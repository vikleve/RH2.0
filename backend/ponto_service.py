# -*- coding: utf-8 -*-
"""
Serviço Dedicado dos Módulos 03, 04 e 05 — Ponto Eletrônico, Ausências, Horas Extras e Adicionais (RF021 a RF050)
Cobre:
- RF021/RF022: Importação AFD/CSV/TXT e API idempotente de marcações, validação e integridade SHA-256
- RF023/RF050: Validação de duplicidades, batidas ímpares, tolerância 5m/10m (CLT art. 58 §1º), intrajornada (art. 71),
               interjornada 11h (art. 66) e limite diário de 2h extras (art. 59)
- RF024..RF026: Ocorrências, ajustes manuais bloqueados em competência fechada, segregação RN-080 e histórico
- RF027..RF030: Espelho real diário/mensal com memória de cálculo e CSV, fechamento com lock, reabertura justificada,
               banco de horas e histórico de alterações
- RF031..RF040: Faltas justificadas/injustificadas/abonadas (art. 473 CLT), atrasos, saídas antecipadas, DSR (Lei 605/49),
               atestados com CID, fluxo de justificativas com aprovação, relatórios de ausências e alerta setorial
- RF041..RF050: Horas extras 50%/100%, trabalho em feriado, adicional noturno com hora ficta (52m30s) e prorrogação
               (Súmula 60 TST), sobreaviso 1/3 (art. 244 §2º), periculosidade, insalubridade e médias variáveis (férias/13º)
"""
import base64
import calendar
import csv
import hashlib
import io
import json
import os
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Callable, Dict, List, Optional, Tuple

from .database import _usar_postgres, fetchall_dict, fetchone_dict, get_connection, init_db, insert_returning_id, ph
from .folha_calculos import (
    arredondar_moeda,
    calcular_adicional_noturno,
    calcular_dsr_sobre_variaveis,
    calcular_horas_extras,
    calcular_insalubridade,
    calcular_periculosidade,
    calcular_prorrogacao_noturna,
    calcular_sobreaviso,
    calcular_trabalho_feriado,
)
from .plataforma_exceptions import (
    PlataformaAcessoNegadoException,
    PlataformaRecursoNaoEncontradoException,
    PlataformaValidacaoException,
)
from .tabelas_legais_service import TabelasLegaisService

TIPOS_REGISTRO_VALIDOS = {"automatico", "relogio_afd", "api", "manual"}
TIPOS_MARCACAO_VALIDOS = {"ENTRADA_1", "SAIDA_1", "ENTRADA_2", "SAIDA_2", "entrada", "saida", "intervalo_inicio", "intervalo_fim"}
CATALOGO_ABONO_CLT_473 = {
    "falecimento_conjuge_asc_desc": (2, "CLT art. 473 I — Falecimento de cônjuge/ascendente/descendente/irmão"),
    "casamento": (3, "CLT art. 473 II — Casamento"),
    "nascimento_filho": (5, "CLT art. 473 III / ADCT art. 10 §1º — Licença-paternidade / nascimento"),
    "doacao_sangue": (1, "CLT art. 473 IV — Doação voluntária de sangue"),
    "alistamento_eleitoral": (2, "CLT art. 473 V — Alistamento eleitoral"),
    "servico_militar": (1, "CLT art. 473 VI — Comparecimento para serviço militar"),
    "vestibular": (1, "CLT art. 473 VII — Prova de exame vestibular"),
    "comparecimento_juizo": (1, "CLT art. 473 VIII — Comparecimento em juízo"),
    "consulta_pre_natal": (6, "CLT art. 473 X — Acompanhamento consulta pré-natal esposa/companheira"),
    "acompanhamento_filho": (1, "CLT art. 473 XI — Acompanhamento de filho até 6 anos em consulta médica"),
    "exame_preventivo_cancer": (3, "CLT art. 473 XII — Exames preventivos de câncer"),
}
DIAS_SEMANA_PT = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]


def _hora_para_min(hhmm: str) -> Optional[int]:
    m = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$", str(hhmm or "").strip())
    if not m:
        return None
    h, mn = int(m.group(1)), int(m.group(2))
    if h < 0 or h > 23 or mn < 0 or mn > 59:
        return None
    return h * 60 + mn


def _min_para_hhmm(minutos: int) -> str:
    h = (minutos // 60) % 24
    m = minutos % 60
    return f"{h:02d}:{m:02d}"


def _normalizar_hora_hms(hhmm: str) -> Optional[str]:
    m = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$", str(hhmm or "").strip())
    if not m:
        return None
    h, mn, sg = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    if h < 0 or h > 23 or mn < 0 or mn > 59 or sg < 0 or sg > 59:
        return None
    return f"{h:02d}:{mn:02d}:{sg:02d}"


def _ordenar_marcacoes_dia(regs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ordena batidas do dia respeitando tipo_marcacao ou turno noturno iniciado >= 18h."""
    ordem_tm = {
        "ENTRADA_1": 1, "ENTRADA": 1,
        "SAIDA_1": 2, "INTERVALO_INICIO": 2,
        "ENTRADA_2": 3, "INTERVALO_FIM": 3,
        "SAIDA_2": 4, "SAIDA": 4,
    }
    if any(r.get("tipo_marcacao") for r in regs) and all(
        (r.get("tipo_marcacao") or "").upper() in ordem_tm
        for r in regs if r.get("tipo_marcacao")
    ):
        return sorted(regs, key=lambda r: (ordem_tm.get((r.get("tipo_marcacao") or "").upper(), 9), r["hora"][:5]))
    mins_id = [(_hora_para_min(r["hora"][:5]) or 0) for r in regs]
    if mins_id and mins_id[0] >= 18 * 60 and any(m <= 12 * 60 for m in mins_id[1:]):
        return regs
    return sorted(regs, key=lambda r: r["hora"][:5])


def _minutos_intervalo_noturno(inicio_min: int, fim_min: int) -> Tuple[int, int]:
    """
    Calcula separadamente:
    - minutos noturnos estritos entre 22h00 e 05h00
    - minutos prorrogados após 05h00 quando a jornada iniciou em período noturno e avançou após 05h00 (Súmula 60 TST)
    """
    if fim_min <= inicio_min:
        fim_min += 1440
    min_noturno = 0
    min_prorrogado = 0
    iniciou_noturno = False
    for minuto in range(inicio_min, fim_min):
        mod = minuto % 1440
        eh_not = (mod >= 22 * 60) or (mod < 5 * 60)
        if minuto == inicio_min and eh_not:
            iniciou_noturno = True
        if eh_not:
            min_noturno += 1
        elif iniciou_noturno and (5 * 60 <= mod < 12 * 60) and min_noturno >= 60:
            min_prorrogado += 1
    return min_noturno, min_prorrogado


class PontoService:
    def __init__(
        self,
        db_path: Optional[str] = None,
        auditoria_cb: Optional[Callable[..., None]] = None,
    ):
        self.db_path = db_path
        self._auditoria_cb = auditoria_cb
        init_db(db_path=self.db_path)

    def _conn(self):
        return get_connection(self.db_path)

    def _pg(self) -> bool:
        return _usar_postgres(self.db_path)

    def _p(self) -> str:
        return "%s" if self._pg() else "?"

    def _auditar(self, **kwargs):
        if self._auditoria_cb:
            self._auditoria_cb(**kwargs)

    def _buscar_colab(self, cur, colaborador_id: int, empresa_id: Optional[str] = None) -> Dict[str, Any]:
        p = self._p()
        sql = f"SELECT * FROM colaboradores WHERE id = {p}"
        params: List[Any] = [int(colaborador_id)]
        if empresa_id:
            sql += f" AND COALESCE(empresa_id, 'a0000000-0000-0000-0000-000000000001') = {p}"
            params.append(empresa_id)
        cur.execute(sql + ";", tuple(params))
        colab = fetchone_dict(cur, self.db_path)
        if not colab:
            raise PlataformaRecursoNaoEncontradoException("Colaborador não encontrado.")
        return colab

    def _verificar_periodo_fechado(self, cur, empresa_id: str, competencia: str):
        p = self._p()
        cur.execute(
            f"""
            SELECT * FROM fechamentos_ponto
            WHERE empresa_id = {p} AND competencia = {p} AND situacao = 'fechado'
            ORDER BY id DESC LIMIT 1;
        """,
            (empresa_id, competencia[:7]),
        )
        fech = fetchone_dict(cur, self.db_path)
        if fech:
            raise PlataformaValidacaoException(
                f"Competência {competencia[:7]} está fechada (fechamento #{fech['id']} por {fech['fechado_por']}). "
                "Solicite reabertura autorizada antes de alterar marcações, ajustes ou ocorrências (RF028/RF029)."
            )

    def _registrar_historico_jornada(
        self,
        cur,
        empresa_id: str,
        colaborador_id: int,
        competencia: str,
        evento: str,
        valor_anterior: Optional[str],
        valor_novo: Optional[str],
        justificativa: Optional[str],
        usuario: str,
    ):
        p = self._p()
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            f"""
            INSERT INTO ponto_historico_jornada (
                empresa_id, colaborador_id, competencia, evento, valor_anterior, valor_novo, justificativa, usuario, criado_em
            ) VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p});
        """,
            (empresa_id, int(colaborador_id), competencia[:7], evento, valor_anterior, valor_novo, justificativa, usuario, agora),
        )

    # ─────────────────────────────────────────────────────────────────────────
    # RF021 / RF022: Registro Individual, Importação por Arquivo e Importação API
    # ─────────────────────────────────────────────────────────────────────────
    def registrar_marcacao_ponto(
        self,
        colaborador_id: int,
        data: str,
        hora: str,
        tipo_registro: str = "manual",
        coletor_id: Optional[str] = None,
        tipo_marcacao: Optional[str] = None,
        arquivo_origem: Optional[str] = None,
        lote_importacao_id: Optional[int] = None,
        idempotency_key: Optional[str] = None,
        usuario: str = "Sistema",
        empresa_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """RF021/RF022: Registra batida de ponto preservando origem, integridade e bloqueando período fechado."""
        dt_str = str(data or "").strip()[:10]
        try:
            datetime.strptime(dt_str, "%Y-%m-%d")
        except ValueError:
            raise PlataformaValidacaoException(f"Data da marcação inválida: '{data}'. Use AAAA-MM-DD.")
        hora_hms = _normalizar_hora_hms(hora)
        if not hora_hms:
            raise PlataformaValidacaoException(f"Horário inválido: '{hora}'. Use HH:MM ou HH:MM:SS.")

        raw_tr = str(tipo_registro or "manual").strip()
        # Compatibilidade: se frontend enviar ENTRADA_1..SAIDA_2 em tipo_registro, move para tipo_marcacao
        if raw_tr.upper() in ("ENTRADA_1", "SAIDA_1", "ENTRADA_2", "SAIDA_2") or raw_tr.lower() in (
            "entrada", "saida", "intervalo_inicio", "intervalo_fim"
        ):
            tipo_marc_eff = tipo_marcacao or raw_tr
            tipo_reg_eff = "manual"
        else:
            tipo_reg_eff = raw_tr.lower() if raw_tr.lower() in TIPOS_REGISTRO_VALIDOS else "manual"
            tipo_marc_eff = tipo_marcacao

        hash_m = hashlib.sha256(f"{int(colaborador_id)}|{dt_str}|{hora_hms[:5]}".encode("utf-8")).hexdigest()

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            colab = self._buscar_colab(cur, int(colaborador_id), empresa_id=empresa_id)
            emp_id = colab.get("empresa_id") or "a0000000-0000-0000-0000-000000000001"
            self._verificar_periodo_fechado(cur, emp_id, dt_str[:7])

            if idempotency_key:
                cur.execute(
                    f"SELECT id FROM marcacoes_ponto WHERE idempotency_key = {p} AND colaborador_id = {p};",
                    (idempotency_key, int(colaborador_id)),
                )
                if cur.fetchone():
                    return {"sucesso": False, "duplicado": True, "mensagem": "Requisição idempotente já processada (RF022)."}

            cur.execute(
                f"SELECT COUNT(*) FROM marcacoes_ponto WHERE colaborador_id = {p} AND data = {p} AND (hora = {p} OR substr(hora,1,5) = {p});",
                (int(colaborador_id), dt_str, hora_hms, hora_hms[:5]),
            )
            if cur.fetchone()[0] > 0:
                return {"sucesso": False, "duplicado": True, "mensagem": "Marcação idêntica já registrada anteriormente (RF022, idempotência)."}

            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sql_pg = f"""
                INSERT INTO marcacoes_ponto (
                    empresa_id, colaborador_id, data, hora, tipo_registro, tipo_marcacao,
                    id_coletor, arquivo_origem, lote_importacao_id, origem_detalhe,
                    idempotency_key, hash_marcacao, inconsistente, criado_em
                ) VALUES ({','.join([p]*14)}) RETURNING id;
            """
            sql_sq = f"""
                INSERT INTO marcacoes_ponto (
                    empresa_id, colaborador_id, data, hora, tipo_registro, tipo_marcacao,
                    id_coletor, arquivo_origem, lote_importacao_id, origem_detalhe,
                    idempotency_key, hash_marcacao, inconsistente, criado_em
                ) VALUES ({','.join([p]*14)});
            """
            m_id = insert_returning_id(
                cur,
                conn,
                sql_pg,
                sql_sq,
                (
                    emp_id, int(colaborador_id), dt_str, hora_hms, tipo_reg_eff, tipo_marc_eff,
                    coletor_id, arquivo_origem, lote_importacao_id, f"{tipo_reg_eff}:{coletor_id or 'sistema'}",
                    idempotency_key, hash_m, 0, agora,
                ),
                self.db_path,
            )
            self._registrar_historico_jornada(
                cur, emp_id, int(colaborador_id), dt_str[:7], "marcacao_ponto", None,
                f"{dt_str} {hora_hms} ({tipo_reg_eff}/{tipo_marc_eff or '-'})", None, usuario,
            )
            conn.commit()
        finally:
            conn.close()

        self._auditar(
            modulo="Ponto",
            operacao="marcacao",
            registro_tipo="marcacoes_ponto",
            registro_id=m_id,
            usuario=usuario,
            valor_novo=f"{dt_str} {hora_hms} ({tipo_reg_eff})",
            detalhes=f"Marcação registrada para colaborador #{colaborador_id} em {dt_str} {hora_hms}.",
            empresa_id=emp_id,
        )
        return {"sucesso": True, "marcacao_id": m_id, "data": dt_str, "hora": hora_hms, "tipo_registro": tipo_reg_eff, "tipo_marcacao": tipo_marc_eff}

    def importar_arquivo_ponto(
        self,
        nome_arquivo: str,
        conteudo_texto_ou_base64: str,
        eh_base64: bool = False,
        usuario: str = "Operador Ponto",
        empresa_id: str = "a0000000-0000-0000-0000-000000000001",
    ) -> Dict[str, Any]:
        """RF021: Importa arquivo de ponto (.csv, .txt ou .afd simplificado) validando formato, colaboradores e duplicidades."""
        nome_arq = str(nome_arquivo or "").strip()
        if not nome_arq or not re.search(r"\.(csv|txt|afd)$", nome_arq, re.IGNORECASE):
            raise PlataformaValidacaoException("Formato de arquivo inválido para importação de ponto. Utilize .csv, .txt ou .afd.")

        if eh_base64:
            try:
                raw_bytes = base64.b64decode(conteudo_texto_ou_base64, validate=True)
                texto = raw_bytes.decode("utf-8", errors="replace")
            except Exception:
                raise PlataformaValidacaoException("Conteúdo base64 do arquivo de ponto inválido.")
        else:
            texto = str(conteudo_texto_ou_base64 or "")
            raw_bytes = texto.encode("utf-8")

        if not texto.strip():
            raise PlataformaValidacaoException("O arquivo de ponto está vazio.")

        sha_arq = hashlib.sha256(raw_bytes).hexdigest()
        linhas = [ln.strip() for ln in texto.splitlines() if ln.strip()]
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(
                f"SELECT id FROM ponto_lotes_importacao WHERE empresa_id = {p} AND sha256_hash = {p};",
                (empresa_id, sha_arq),
            )
            lote_existente = cur.fetchone()
            if lote_existente:
                raise PlataformaValidacaoException(
                    f"Arquivo já importado anteriormente (Lote #{lote_existente[0]}, SHA-256 {sha_arq[:12]})."
                )

            sql_lote_pg = f"""
                INSERT INTO ponto_lotes_importacao (
                    empresa_id, origem, nome_arquivo, sha256_hash, total_registros,
                    total_importados, total_duplicados, total_erros, status, importado_por, importado_em
                ) VALUES ({p},'arquivo',{p},{p},0,0,0,0,'processando',{p},{p}) RETURNING id;
            """
            sql_lote_sq = f"""
                INSERT INTO ponto_lotes_importacao (
                    empresa_id, origem, nome_arquivo, sha256_hash, total_registros,
                    total_importados, total_duplicados, total_erros, status, importado_por, importado_em
                ) VALUES ({p},'arquivo',{p},{p},0,0,0,0,'processando',{p},{p});
            """
            lote_id = insert_returning_id(cur, conn, sql_lote_pg, sql_lote_sq, (empresa_id, nome_arq, sha_arq, usuario, agora), self.db_path)

            # Mapa de colaboradores da empresa (matricula/cpf/id)
            cur.execute(
                f"SELECT id, matricula, cpf FROM colaboradores WHERE COALESCE(empresa_id, 'a0000000-0000-0000-0000-000000000001') = {p};",
                (empresa_id,),
            )
            colabs = fetchall_dict(cur, self.db_path)
            mapa_mat = {str(c["matricula"]).strip().upper(): int(c["id"]) for c in colabs if c.get("matricula")}
            mapa_cpf = {re.sub(r"\D", "", str(c["cpf"] or "")): int(c["id"]) for c in colabs if c.get("cpf")}
            ids_empresa = {int(c["id"]) for c in colabs}
            conn.commit()
        finally:
            conn.close()

        importados = 0
        duplicados = 0
        erros: List[Dict[str, Any]] = []
        total_regs = 0

        for idx, ln in enumerate(linhas, start=1):
            if idx == 1 and ("matricula" in ln.lower() or "cpf" in ln.lower() or "data" in ln.lower()):
                continue
            total_regs += 1
            cid_resolvido = None
            dt_str = ""
            hr_str = ""
            tipo_marc = None
            coletor = "RELOGIO_ARQ"

            # Suporte a AFD simplificado (linha tipo 3: NNNNNNNNN3DDMMYYYYHHMMPIS) ou CSV/TXT (sep ; ou ,)
            m_afd = re.match(r"^\d{9}3(\d{2})(\d{2})(\d{4})(\d{2})(\d{2})(\d{11,12})$", ln)
            if m_afd:
                dd, mm, yyyy, hh, mn, pis_dig = m_afd.groups()
                dt_str = f"{yyyy}-{mm}-{dd}"
                hr_str = f"{hh}:{mn}:00"
                conn_pis = self._conn()
                try:
                    c_pis = conn_pis.cursor()
                    c_pis.execute(
                        f"SELECT id FROM colaboradores WHERE COALESCE(empresa_id,'a0000000-0000-0000-0000-000000000001') = {self._p()} AND REPLACE(REPLACE(COALESCE(pis_pasep,''),'.',''),'-','') LIKE {self._p()};",
                        (empresa_id, f"%{pis_dig[-11:]}"),
                    )
                    r_p = c_pis.fetchone()
                    if r_p:
                        cid_resolvido = int(r_p[0])
                finally:
                    conn_pis.close()
            else:
                sep = ";" if ";" in ln else ","
                partes = [pt.strip() for pt in next(csv.reader([ln], delimiter=sep))]
                if len(partes) < 3:
                    erros.append({"linha": idx, "conteudo": ln, "erro": "Colunas insuficientes (esperado: identificador;data;hora[;tipo_marcacao;coletor])."})
                    continue
                ident, dt_raw, hr_raw = partes[0], partes[1], partes[2]
                tipo_marc = partes[3] if len(partes) > 3 and partes[3] else None
                coletor = partes[4] if len(partes) > 4 and partes[4] else coletor
                # Aceitar DD/MM/AAAA ou AAAA-MM-DD
                if re.match(r"^\d{2}/\d{2}/\d{4}$", dt_raw):
                    d, m, y = dt_raw.split("/")
                    dt_str = f"{y}-{m}-{d}"
                else:
                    dt_str = dt_raw
                hr_str = hr_raw

                ident_up = ident.upper()
                ident_dig = re.sub(r"\D", "", ident)
                if ident.isdigit() and int(ident) in ids_empresa:
                    cid_resolvido = int(ident)
                elif ident_up in mapa_mat:
                    cid_resolvido = mapa_mat[ident_up]
                elif ident_dig in mapa_cpf:
                    cid_resolvido = mapa_cpf[ident_dig]

            if not cid_resolvido:
                erros.append({"linha": idx, "conteudo": ln, "erro": "Colaborador não encontrado ou pertence a outra empresa."})
                continue

            try:
                res_m = self.registrar_marcacao_ponto(
                    colaborador_id=cid_resolvido,
                    data=dt_str,
                    hora=hr_str,
                    tipo_registro="relogio_afd",
                    coletor_id=coletor,
                    tipo_marcacao=tipo_marc,
                    arquivo_origem=nome_arq,
                    lote_importacao_id=lote_id,
                    usuario=usuario,
                    empresa_id=empresa_id,
                )
                if res_m.get("sucesso"):
                    importados += 1
                elif res_m.get("duplicado"):
                    duplicados += 1
            except Exception as exc:
                erros.append({"linha": idx, "conteudo": ln, "erro": str(exc)})

        status_lote = "processado_com_ressalvas" if erros else "processado"
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(
                f"""
                UPDATE ponto_lotes_importacao
                SET total_registros = {p}, total_importados = {p}, total_duplicados = {p},
                    total_erros = {p}, erros_json = {p}, status = {p}
                WHERE id = {p};
            """,
                (total_regs, importados, duplicados, len(erros), json.dumps(erros, ensure_ascii=False), status_lote, lote_id),
            )
            conn.commit()
        finally:
            conn.close()

        self._auditar(
            modulo="Ponto",
            operacao="importacao_arquivo",
            registro_tipo="ponto_lotes_importacao",
            registro_id=lote_id,
            usuario=usuario,
            valor_novo=f"{importados} importadas / {duplicados} dup / {len(erros)} erros",
            detalhes=f"Arquivo '{nome_arq}' (SHA-256: {sha_arq[:12]}) importado.",
            empresa_id=empresa_id,
        )
        return {
            "sucesso": True,
            "lote_id": lote_id,
            "nome_arquivo": nome_arq,
            "sha256_hash": sha_arq,
            "total_registros": total_regs,
            "total_importados": importados,
            "total_duplicados": duplicados,
            "total_erros": len(erros),
            "erros": erros,
            "status": status_lote,
        }

    def importar_marcacoes_api(
        self,
        marcacoes: List[Dict[str, Any]],
        idempotency_key: str,
        coletor_id: str = "API_EXTERNA",
        usuario: str = "Integração API",
        empresa_id: str = "a0000000-0000-0000-0000-000000000001",
    ) -> Dict[str, Any]:
        """RF022: Recebe lote via API garantindo idempotência, rastreabilidade de origem e validação."""
        chave = str(idempotency_key or "").strip()
        if not chave:
            raise PlataformaValidacaoException("Cabeçalho ou campo 'idempotency_key' é obrigatório na importação via API (RF022).")
        if not isinstance(marcacoes, list) or not marcacoes:
            raise PlataformaValidacaoException("Informe uma lista não vazia de marcações.")

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(
                f"SELECT * FROM ponto_lotes_importacao WHERE empresa_id = {p} AND idempotency_key = {p};",
                (empresa_id, chave),
            )
            lote_prev = fetchone_dict(cur, self.db_path)
            if lote_prev:
                return {
                    "sucesso": True,
                    "idempotente_reaproveitado": True,
                    "lote_id": lote_prev["id"],
                    "total_importados": lote_prev["total_importados"],
                    "total_duplicados": lote_prev["total_duplicados"],
                    "mensagem": "Lote já processado anteriormente para esta chave de idempotência.",
                }

            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sql_pg = f"""
                INSERT INTO ponto_lotes_importacao (
                    empresa_id, origem, idempotency_key, total_registros, total_importados,
                    total_duplicados, total_erros, status, importado_por, importado_em
                ) VALUES ({p},'api',{p},{p},0,0,0,'processando',{p},{p}) RETURNING id;
            """
            sql_sq = f"""
                INSERT INTO ponto_lotes_importacao (
                    empresa_id, origem, idempotency_key, total_registros, total_importados,
                    total_duplicados, total_erros, status, importado_por, importado_em
                ) VALUES ({p},'api',{p},{p},0,0,0,'processando',{p},{p});
            """
            lote_id = insert_returning_id(cur, conn, sql_pg, sql_sq, (empresa_id, chave, len(marcacoes), usuario, agora), self.db_path)
            conn.commit()
        finally:
            conn.close()

        imp = 0
        dup = 0
        errs = []
        for idx, item in enumerate(marcacoes, start=1):
            try:
                cid = int(item.get("colaborador_id"))
                res = self.registrar_marcacao_ponto(
                    colaborador_id=cid,
                    data=item.get("data"),
                    hora=item.get("hora"),
                    tipo_registro="api",
                    coletor_id=item.get("coletor_id") or coletor_id,
                    tipo_marcacao=item.get("tipo_marcacao"),
                    lote_importacao_id=lote_id,
                    idempotency_key=f"{chave}:{idx}:{cid}",
                    usuario=usuario,
                    empresa_id=empresa_id,
                )
                if res.get("sucesso"):
                    imp += 1
                else:
                    dup += 1
            except Exception as exc:
                errs.append({"indice": idx, "erro": str(exc)})

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(
                f"""
                UPDATE ponto_lotes_importacao
                SET total_importados = {p}, total_duplicados = {p}, total_erros = {p},
                    erros_json = {p}, status = {p}
                WHERE id = {p};
            """,
                (imp, dup, len(errs), json.dumps(errs, ensure_ascii=False), "processado_com_ressalvas" if errs else "processado", lote_id),
            )
            conn.commit()
        finally:
            conn.close()

        return {
            "sucesso": True,
            "idempotente_reaproveitado": False,
            "lote_id": lote_id,
            "total_registros": len(marcacoes),
            "total_importados": imp,
            "total_duplicados": dup,
            "total_erros": len(errs),
            "erros": errs,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # RF023 / RF024 / RF050: Validação de Marcações (Tolerância, Intra, Inter, Limite 2h)
    # ─────────────────────────────────────────────────────────────────────────
    def validar_marcacoes_periodo(
        self,
        colaborador_id: int,
        competencia: str,
        empresa_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """RF023/RF050: Audita marcações do mês verificando ímpares, duplicidades, intrajornada, interjornada 11h e >2h extras."""
        espelho = self.obter_espelho_ponto(colaborador_id, competencia, empresa_id=empresa_id)
        inconsistencias: List[Dict[str, Any]] = []

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(f"UPDATE marcacoes_ponto SET inconsistente = 0, motivo_inconsistencia = NULL WHERE colaborador_id = {p} AND data LIKE {p};", (colaborador_id, f"{competencia[:7]}%"))

            for dia in espelho["grade_dias"]:
                dt = dia["data"]
                bats = dia["batidas"]
                probs = []
                if len(bats) % 2 != 0:
                    probs.append(f"Marcações ímpares ({len(bats)} batida(s)) — falta entrada ou saída.")
                if dia.get("intrajornada_violada"):
                    probs.append(f"Intrajornada inferior ao mínimo legal para jornada > 6h ({dia.get('intervalo_real_min', 0)} min — CLT art. 71).")
                if dia.get("interjornada_violada"):
                    probs.append(f"Descanso interjornada inferior a 11h ({dia.get('interjornada_horas', 0)}h — CLT art. 66).")
                if dia.get("limite_2h_extras_excedido"):
                    probs.append(f"Limite diário de 2h extras excedido ({dia.get('he_total_dia', 0)}h extras — CLT art. 59).")
                if probs:
                    msg = " | ".join(probs)
                    cur.execute(
                        f"UPDATE marcacoes_ponto SET inconsistente = 1, motivo_inconsistencia = {p} WHERE colaborador_id = {p} AND data = {p};",
                        (msg, colaborador_id, dt),
                    )
                    inconsistencias.append({"data": dt, "problemas": probs})
            conn.commit()
        finally:
            conn.close()

        return {
            "sucesso": True,
            "colaborador_id": int(colaborador_id),
            "competencia": competencia[:7],
            "total_inconsistencias": len(inconsistencias),
            "inconsistencias": inconsistencias,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # RF025 / RF026: Solicitação e Aprovação de Ajustes
    # ─────────────────────────────────────────────────────────────────────────
    def listar_ajustes_ponto(
        self,
        empresa_id: Optional[str] = None,
        colaborador_id: Optional[int] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            sql = """
                SELECT a.*, c.nome_completo AS colaborador_nome, c.matricula AS colaborador_matricula, c.setor
                FROM ajustes_ponto a
                JOIN colaboradores c ON c.id = a.colaborador_id
                WHERE 1=1
            """
            params: List[Any] = []
            if empresa_id:
                sql += f" AND COALESCE(c.empresa_id, 'a0000000-0000-0000-0000-000000000001') = {p}"
                params.append(empresa_id)
            if colaborador_id:
                sql += f" AND a.colaborador_id = {p}"
                params.append(int(colaborador_id))
            if status:
                sql += f" AND LOWER(a.status) = LOWER({p})"
                params.append(status.strip())
            sql += " ORDER BY a.id DESC;"
            cur.execute(sql, tuple(params))
            return fetchall_dict(cur, self.db_path)
        finally:
            conn.close()

    def solicitar_ajuste_ponto(
        self,
        colaborador_id: int,
        data: str,
        hora_ajustada: str,
        tipo_marcacao: str,
        motivo: str,
        solicitante: str,
        hora_original: Optional[str] = None,
        solicitante_usuario_id: Optional[int] = None,
        empresa_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """RF025: Solicitação de ajuste de ponto com justificativa obrigatória e proteção contra período fechado."""
        if not motivo or not motivo.strip():
            raise PlataformaValidacaoException("Justificativa é estritamente obrigatória para ajuste manual de ponto (RF-025, RN-013).")
        dt_str = str(data or "").strip()[:10]
        try:
            datetime.strptime(dt_str, "%Y-%m-%d")
        except ValueError:
            raise PlataformaValidacaoException("Data do ajuste inválida (use AAAA-MM-DD).")
        hora_hms = _normalizar_hora_hms(hora_ajustada)
        if not hora_hms:
            raise PlataformaValidacaoException("Horário ajustado inválido (use HH:MM ou HH:MM:SS).")

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            colab = self._buscar_colab(cur, int(colaborador_id), empresa_id=empresa_id)
            emp_id = colab.get("empresa_id") or "a0000000-0000-0000-0000-000000000001"
            self._verificar_periodo_fechado(cur, emp_id, dt_str[:7])

            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sql_pg = f"""
                INSERT INTO ajustes_ponto (
                    empresa_id, colaborador_id, data, hora_original, hora_ajustada, tipo_marcacao,
                    motivo, status, solicitante_usuario_id, criado_por, criado_em, atualizado_em
                ) VALUES ({p},{p},{p},{p},{p},{p},{p},'pendente',{p},{p},{p},{p}) RETURNING id;
            """
            sql_sqlite = f"""
                INSERT INTO ajustes_ponto (
                    empresa_id, colaborador_id, data, hora_original, hora_ajustada, tipo_marcacao,
                    motivo, status, solicitante_usuario_id, criado_por, criado_em, atualizado_em
                ) VALUES ({p},{p},{p},{p},{p},{p},{p},'pendente',{p},{p},{p},{p});
            """
            params = (emp_id, int(colaborador_id), dt_str, hora_original, hora_hms, str(tipo_marcacao or "entrada"), motivo.strip(), solicitante_usuario_id, solicitante, agora, agora)
            ajuste_id = insert_returning_id(cur, conn, sql_pg, sql_sqlite, params, self.db_path)
            self._registrar_historico_jornada(
                cur, emp_id, int(colaborador_id), dt_str[:7], "solicitacao_ajuste",
                hora_original or "ausente", hora_hms, motivo.strip(), solicitante,
            )
            conn.commit()
        finally:
            conn.close()

        self._auditar(
            modulo="Ponto",
            operacao="inclusao",
            registro_tipo="ajustes_ponto",
            registro_id=ajuste_id,
            usuario=solicitante,
            detalhes=f"Ajuste solicitado para Colaborador {colaborador_id} em {dt_str}: {hora_hms} ({motivo})",
            empresa_id=emp_id,
        )
        return {"sucesso": True, "ajuste_id": ajuste_id, "mensagem": "Ajuste de ponto submetido para aprovação do gestor/DP."}

    def aprovar_ajuste_ponto(
        self,
        ajuste_id: int,
        aprovador: str,
        aprovar: bool = True,
        motivo_reprovacao: Optional[str] = None,
        aprovador_usuario_id: Optional[int] = None,
        empresa_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """RF026: Aprovação ou reprovação de ajuste de ponto com segregação (RN-080) e anti-reprocessamento."""
        if not aprovar and not (motivo_reprovacao and str(motivo_reprovacao).strip()):
            raise PlataformaValidacaoException("Motivo da reprovação é obrigatório ao rejeitar ajuste de ponto.")

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(f"SELECT * FROM ajustes_ponto WHERE id = {p};", (int(ajuste_id),))
            ajuste = fetchone_dict(cur, self.db_path)
            if not ajuste:
                raise PlataformaRecursoNaoEncontradoException("Ajuste de ponto não encontrado.")

            colab = self._buscar_colab(cur, int(ajuste["colaborador_id"]), empresa_id=empresa_id)
            emp_id = colab.get("empresa_id") or "a0000000-0000-0000-0000-000000000001"
            self._verificar_periodo_fechado(cur, emp_id, ajuste["data"][:7])

            if str(ajuste["status"]).lower() != "pendente":
                raise PlataformaValidacaoException(f"Ajuste #{ajuste_id} já foi finalizado com status '{ajuste['status']}'.")

            if (aprovador_usuario_id and ajuste.get("solicitante_usuario_id") and int(aprovador_usuario_id) == int(ajuste["solicitante_usuario_id"])) or (
                str(ajuste["criado_por"]).strip().lower() == str(aprovador).strip().lower()
            ):
                raise PlataformaAcessoNegadoException("Autoaprovação de ajuste de ponto é proibida (RN-080, RF-026).")

            novo_status = "aprovado" if aprovar else "reprovado"
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            cur.execute(
                f"""
                UPDATE ajustes_ponto
                SET status = {p}, aprovado_por = {p}, aprovado_em = {p}, aprovador_usuario_id = {p},
                    motivo_reprovacao = {p}, atualizado_em = {p}
                WHERE id = {p};
            """,
                (novo_status, aprovador, agora, aprovador_usuario_id, motivo_reprovacao, agora, int(ajuste_id)),
            )

            if aprovar:
                h_hms = _normalizar_hora_hms(ajuste["hora_ajustada"]) or ajuste["hora_ajustada"]
                h_hash = hashlib.sha256(f"{ajuste['colaborador_id']}|{ajuste['data']}|{h_hms[:5]}".encode("utf-8")).hexdigest()
                # Se houver marcação original com hora_original informada, preserva rastreio atualizando-a ou inserindo nova
                if ajuste.get("hora_original"):
                    orig_hms = _normalizar_hora_hms(ajuste["hora_original"]) or ajuste["hora_original"]
                    cur.execute(
                        f"""
                        UPDATE marcacoes_ponto
                        SET hora = {p}, tipo_marcacao = {p}, editada_por_ajuste_id = {p}, origem_detalhe = {p}, hash_marcacao = {p}
                        WHERE colaborador_id = {p} AND data = {p} AND substr(hora,1,5) = {p};
                    """,
                        (h_hms, ajuste["tipo_marcacao"], int(ajuste_id), f"ajuste_aprovado_de:{orig_hms}", h_hash, int(ajuste["colaborador_id"]), ajuste["data"], orig_hms[:5]),
                    )
                if cur.rowcount == 0:
                    cur.execute(
                        f"""
                        INSERT INTO marcacoes_ponto (
                            empresa_id, colaborador_id, data, hora, tipo_registro, tipo_marcacao,
                            id_coletor, origem_detalhe, hash_marcacao, editada_por_ajuste_id, criado_em
                        ) VALUES ({p},{p},{p},{p},'manual',{p},'ajuste_aprovado',{p},{p},{p},{p});
                    """,
                        (emp_id, ajuste["colaborador_id"], ajuste["data"], h_hms, ajuste["tipo_marcacao"], f"ajuste #{ajuste_id} por {aprovador}", h_hash, int(ajuste_id), agora),
                    )

            self._registrar_historico_jornada(
                cur, emp_id, int(ajuste["colaborador_id"]), ajuste["data"][:7],
                f"ajuste_{novo_status}", ajuste.get("hora_original") or "-", ajuste["hora_ajustada"],
                motivo_reprovacao or ajuste["motivo"], aprovador,
            )
            conn.commit()
        finally:
            conn.close()

        self._auditar(
            modulo="Ponto",
            operacao="aprovacao" if aprovar else "reprovacao",
            registro_tipo="ajustes_ponto",
            registro_id=ajuste_id,
            usuario=aprovador,
            valor_anterior="pendente",
            valor_novo=novo_status,
            detalhes=f"Ajuste {ajuste_id} {novo_status} por {aprovador}.",
            empresa_id=emp_id,
        )
        return {"sucesso": True, "status": novo_status, "mensagem": f"Ajuste de ponto {novo_status} com sucesso."}

    # ─────────────────────────────────────────────────────────────────────────
    # RF031..RF040: Ocorrências (Faltas, Abonos Art. 473, Atestados, Atrasos) e Justificativas
    # ─────────────────────────────────────────────────────────────────────────
    def registrar_ocorrencia(
        self,
        colaborador_id: int,
        data_inicio: str,
        data_fim: Optional[str],
        tipo_ocorrencia: str,
        justificativa: str,
        minutos_ausencia: int = 0,
        cid: Optional[str] = None,
        artigo_clt: Optional[str] = None,
        status: str = "aprovado",
        usuario: str = "DP / RH",
        empresa_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """RF031-RF036: Registra falta justificada/injustificada/abonada, atraso, saída antecipada ou atestado médico."""
        dt_i = str(data_inicio or "").strip()[:10]
        dt_f = str(data_fim or dt_i).strip()[:10]
        try:
            d_i = datetime.strptime(dt_i, "%Y-%m-%d").date()
            d_f = datetime.strptime(dt_f, "%Y-%m-%d").date()
        except ValueError:
            raise PlataformaValidacaoException("Datas inválidas para ocorrência de ponto (use AAAA-MM-DD).")
        if d_f < d_i:
            raise PlataformaValidacaoException("Data final da ocorrência não pode ser anterior à data inicial.")
        if not justificativa or not justificativa.strip():
            raise PlataformaValidacaoException("Justificativa/descrição da ocorrência é obrigatória.")

        tipo_norm = str(tipo_ocorrencia or "").strip().lower()
        tipos_validos = {"falta_injustificada", "falta_justificada", "falta_abonada", "atraso", "saida_antecipada", "atestado", "sobreaviso"}
        if tipo_norm not in tipos_validos:
            raise PlataformaValidacaoException(f"Tipo de ocorrência inválido: '{tipo_ocorrencia}'.")

        dias_tot = (d_f - d_i).days + 1
        if artigo_clt and artigo_clt in CATALOGO_ABONO_CLT_473 and tipo_norm == "falta_abonada":
            lim_dias, desc_clt = CATALOGO_ABONO_CLT_473[artigo_clt]
            if dias_tot > lim_dias:
                raise PlataformaValidacaoException(
                    f"Limite legal excedido para '{desc_clt}': máximo {lim_dias} dia(s), informado {dias_tot}."
                )

        mins = int(minutos_ausencia or 0)
        if mins == 0 and tipo_norm in ("falta_injustificada", "falta_justificada", "falta_abonada", "atestado"):
            mins = dias_tot * 480

        impacta_dsr = 1 if tipo_norm == "falta_injustificada" else 0
        impacta_fer = 1 if tipo_norm == "falta_injustificada" else 0
        impacta_dec = 1 if tipo_norm == "falta_injustificada" else 0
        mem = (
            f"Ocorrência {tipo_norm} ({dt_i} a {dt_f}, {dias_tot}d / {mins}min): "
            f"{'desconta DSR/férias/13º' if impacta_dsr else 'sem perda salarial/DSR'}"
        )

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            colab = self._buscar_colab(cur, int(colaborador_id), empresa_id=empresa_id)
            emp_id = colab.get("empresa_id") or "a0000000-0000-0000-0000-000000000001"
            self._verificar_periodo_fechado(cur, emp_id, dt_i[:7])

            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sql_pg = f"""
                INSERT INTO ocorrencias_ponto (
                    empresa_id, colaborador_id, data_inicio, data_fim, tipo_ocorrencia,
                    minutos_ausencia, minutos, cid, justificativa, desconta_dsr,
                    impacta_dsr, impacta_ferias, impacta_decimo, memoria_calculo,
                    status, aprovado_por, aprovado_em, criado_por, criado_em
                ) VALUES ({','.join([p]*19)}) RETURNING id;
            """
            sql_sq = f"""
                INSERT INTO ocorrencias_ponto (
                    empresa_id, colaborador_id, data_inicio, data_fim, tipo_ocorrencia,
                    minutos_ausencia, minutos, cid, justificativa, desconta_dsr,
                    impacta_dsr, impacta_ferias, impacta_decimo, memoria_calculo,
                    status, aprovado_por, aprovado_em, criado_por, criado_em
                ) VALUES ({','.join([p]*19)});
            """
            aprov_p = usuario if status == "aprovado" else None
            aprov_e = agora if status == "aprovado" else None
            oc_id = insert_returning_id(
                cur,
                conn,
                sql_pg,
                sql_sq,
                (
                    emp_id, int(colaborador_id), dt_i, dt_f, tipo_norm,
                    mins, mins, (cid or "").strip() or None, justificativa.strip(), impacta_dsr,
                    impacta_dsr, impacta_fer, impacta_dec, mem,
                    status, aprov_p, aprov_e, usuario, agora,
                ),
                self.db_path,
            )
            self._registrar_historico_jornada(
                cur, emp_id, int(colaborador_id), dt_i[:7], f"ocorrencia_{tipo_norm}",
                None, f"{dt_i}..{dt_f} ({mins}m)", justificativa.strip(), usuario,
            )
            conn.commit()
        finally:
            conn.close()

        self._auditar(
            modulo="Ponto",
            operacao="ocorrencia",
            registro_tipo="ocorrencias_ponto",
            registro_id=oc_id,
            usuario=usuario,
            valor_novo=f"{tipo_norm} ({dt_i}..{dt_f})",
            detalhes=mem,
            empresa_id=emp_id,
        )
        return {"sucesso": True, "ocorrencia_id": oc_id, "tipo_ocorrencia": tipo_norm, "dias": dias_tot, "impacta_dsr": bool(impacta_dsr), "memoria_calculo": mem}

    def listar_ocorrencias(
        self,
        empresa_id: Optional[str] = None,
        colaborador_id: Optional[int] = None,
        competencia: Optional[str] = None,
        tipo: Optional[str] = None,
        setor: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            sql = """
                SELECT o.*, c.nome_completo AS colaborador_nome, c.matricula AS colaborador_matricula, c.setor
                FROM ocorrencias_ponto o
                JOIN colaboradores c ON c.id = o.colaborador_id
                WHERE 1=1
            """
            params: List[Any] = []
            if empresa_id:
                sql += f" AND COALESCE(c.empresa_id, 'a0000000-0000-0000-0000-000000000001') = {p}"
                params.append(empresa_id)
            if colaborador_id:
                sql += f" AND o.colaborador_id = {p}"
                params.append(int(colaborador_id))
            if competencia:
                comp = competencia.strip()[:7]
                sql += f" AND (o.data_inicio LIKE {p} OR o.data_fim LIKE {p})"
                params.extend([f"{comp}%", f"{comp}%"])
            if tipo:
                sql += f" AND LOWER(o.tipo_ocorrencia) = LOWER({p})"
                params.append(tipo.strip())
            if setor:
                sql += f" AND LOWER(COALESCE(c.setor,'')) = LOWER({p})"
                params.append(setor.strip())
            sql += " ORDER BY o.data_inicio DESC, o.id DESC;"
            cur.execute(sql, tuple(params))
            return fetchall_dict(cur, self.db_path)
        finally:
            conn.close()

    def registrar_justificativa(
        self,
        colaborador_id: int,
        data_referencia: str,
        tipo: str,
        motivo: str,
        solicitante: str,
        cid: Optional[str] = None,
        dias_abono: int = 1,
        artigo_clt: Optional[str] = None,
        empresa_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """RF038: Solicitação formal de justificativa/atestado vinculada a ocorrência de ponto."""
        dt = str(data_referencia or "").strip()[:10]
        try:
            datetime.strptime(dt, "%Y-%m-%d")
        except ValueError:
            raise PlataformaValidacaoException("Data de referência inválida (use AAAA-MM-DD).")
        if not motivo or not motivo.strip():
            raise PlataformaValidacaoException("Motivo da justificativa é obrigatório.")
        tipo_n = str(tipo or "").strip().lower()
        if tipo_n not in ("atestado", "falta_justificada", "falta_abonada", "atraso_justificado", "saida_justificada"):
            raise PlataformaValidacaoException("Tipo de justificativa inválido.")
        if tipo_n == "falta_abonada" and artigo_clt and artigo_clt in CATALOGO_ABONO_CLT_473:
            lim, desc_c = CATALOGO_ABONO_CLT_473[artigo_clt]
            if int(dias_abono or 1) > lim:
                raise PlataformaValidacaoException(f"Dias solicitados excedem limite legal ({lim}d) para {desc_c}.")

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            colab = self._buscar_colab(cur, int(colaborador_id), empresa_id=empresa_id)
            emp_id = colab.get("empresa_id") or "a0000000-0000-0000-0000-000000000001"
            self._verificar_periodo_fechado(cur, emp_id, dt[:7])

            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sql_pg = f"""
                INSERT INTO ponto_justificativas (
                    empresa_id, colaborador_id, data_referencia, tipo, motivo, cid, dias_abono,
                    artigo_clt, status, solicitado_por, criado_em, atualizado_em
                ) VALUES ({p},{p},{p},{p},{p},{p},{p},{p},'pendente',{p},{p},{p}) RETURNING id;
            """
            sql_sq = f"""
                INSERT INTO ponto_justificativas (
                    empresa_id, colaborador_id, data_referencia, tipo, motivo, cid, dias_abono,
                    artigo_clt, status, solicitado_por, criado_em, atualizado_em
                ) VALUES ({p},{p},{p},{p},{p},{p},{p},{p},'pendente',{p},{p},{p});
            """
            jid = insert_returning_id(
                cur, conn, sql_pg, sql_sq,
                (emp_id, int(colaborador_id), dt, tipo_n, motivo.strip(), (cid or "").strip() or None, int(dias_abono or 1), artigo_clt, solicitante, agora, agora),
                self.db_path,
            )
            conn.commit()
        finally:
            conn.close()
        return {"sucesso": True, "justificativa_id": jid, "status": "pendente"}

    def listar_justificativas(
        self,
        empresa_id: Optional[str] = None,
        colaborador_id: Optional[int] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            sql = """
                SELECT j.*, c.nome_completo AS colaborador_nome, c.matricula AS colaborador_matricula
                FROM ponto_justificativas j
                JOIN colaboradores c ON c.id = j.colaborador_id
                WHERE 1=1
            """
            params: List[Any] = []
            if empresa_id:
                sql += f" AND j.empresa_id = {p}"
                params.append(empresa_id)
            if colaborador_id:
                sql += f" AND j.colaborador_id = {p}"
                params.append(int(colaborador_id))
            if status:
                sql += f" AND LOWER(j.status) = LOWER({p})"
                params.append(status.strip())
            sql += " ORDER BY j.id DESC;"
            cur.execute(sql, tuple(params))
            return fetchall_dict(cur, self.db_path)
        finally:
            conn.close()

    def decidir_justificativa(
        self,
        justificativa_id: int,
        aprovador: str,
        aprovar: bool = True,
        motivo_decisao: Optional[str] = None,
        empresa_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """RF039: Aprova/reprova justificativa com bloqueio de autoaprovação e conversão em ocorrência abonada."""
        if not aprovar and not (motivo_decisao and str(motivo_decisao).strip()):
            raise PlataformaValidacaoException("Motivo é obrigatório ao reprovar justificativa.")
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(f"SELECT * FROM ponto_justificativas WHERE id = {p};", (int(justificativa_id),))
            just = fetchone_dict(cur, self.db_path)
            if not just:
                raise PlataformaRecursoNaoEncontradoException("Justificativa não encontrada.")
            if empresa_id and just["empresa_id"] != empresa_id:
                raise PlataformaRecursoNaoEncontradoException("Justificativa não encontrada nesta empresa.")
            if just["status"] != "pendente":
                raise PlataformaValidacaoException(f"Justificativa #{justificativa_id} já decidida ({just['status']}).")
            if str(just["solicitado_por"]).strip().lower() == str(aprovador).strip().lower():
                raise PlataformaAcessoNegadoException("Autoaprovação de justificativa não permitida (RN-080).")

            self._verificar_periodo_fechado(cur, just["empresa_id"], just["data_referencia"][:7])
            novo_st = "aprovado" if aprovar else "reprovado"
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute(
                f"""
                UPDATE ponto_justificativas
                SET status = {p}, aprovado_por = {p}, motivo_decisao = {p}, atualizado_em = {p}
                WHERE id = {p};
            """,
                (novo_st, aprovador, motivo_decisao, agora, int(justificativa_id)),
            )
            dt_ini = datetime.strptime(just["data_referencia"][:10], "%Y-%m-%d").date()
            dt_fim = (dt_ini + timedelta(days=max(1, int(just.get("dias_abono") or 1)) - 1)).isoformat()
            tipo_oc = "falta_abonada" if (aprovar and just["tipo"] == "falta_abonada") else ("falta_justificada" if aprovar else "falta_injustificada")
            impacta = 0 if aprovar else 1
            cur.execute(
                f"""
                INSERT INTO ocorrencias_ponto (
                    empresa_id, colaborador_id, data_inicio, data_fim, tipo_ocorrencia,
                    minutos_ausencia, minutos, cid, justificativa_id, justificativa,
                    desconta_dsr, impacta_dsr, impacta_ferias, impacta_decimo, memoria_calculo,
                    status, aprovado_por, aprovado_em, criado_por, criado_em
                ) VALUES ({','.join([p]*20)});
            """,
                (
                    just["empresa_id"], just["colaborador_id"], just["data_referencia"][:10], dt_fim, tipo_oc,
                    int(just.get("dias_abono") or 1) * 480, int(just.get("dias_abono") or 1) * 480,
                    just.get("cid"), int(justificativa_id), just["motivo"],
                    impacta, impacta, impacta, impacta,
                    f"Gerado por justificativa #{justificativa_id} ({novo_st} por {aprovador})",
                    novo_st, aprovador, agora, just["solicitado_por"], agora,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        self._auditar(
            modulo="Ponto",
            operacao=f"justificativa_{novo_st}",
            registro_tipo="ponto_justificativas",
            registro_id=justificativa_id,
            usuario=aprovador,
            valor_novo=novo_st,
            empresa_id=just["empresa_id"],
        )
        return {"sucesso": True, "justificativa_id": int(justificativa_id), "status": novo_st, "tipo_ocorrencia_gerada": tipo_oc}

    # ─────────────────────────────────────────────────────────────────────────
    # RF029: Banco de Horas
    # ─────────────────────────────────────────────────────────────────────────
    def movimentar_banco_horas(
        self,
        colaborador_id: int,
        data_referencia: str,
        tipo_movimento: str,
        minutos: int,
        observacao: str = "",
        prazo_meses: int = 6,
        usuario: str = "DP",
        empresa_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Registra crédito ou débito/compensação em Banco de Horas (CLT art. 59 §2º/§5º)."""
        tm = str(tipo_movimento or "").strip().lower()
        if tm not in ("credito", "debito", "compensacao"):
            raise PlataformaValidacaoException("Tipo de movimento de banco de horas deve ser credito, debito ou compensacao.")
        mins = int(minutos or 0)
        if mins <= 0:
            raise PlataformaValidacaoException("Quantidade de minutos do banco de horas deve ser positiva.")
        dt_str = str(data_referencia or "").strip()[:10]
        dt_obj = datetime.strptime(dt_str, "%Y-%m-%d").date()
        prazo = (dt_obj + timedelta(days=30 * max(1, int(prazo_meses)))).isoformat()

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            colab = self._buscar_colab(cur, int(colaborador_id), empresa_id=empresa_id)
            emp_id = colab.get("empresa_id") or "a0000000-0000-0000-0000-000000000001"
            cur.execute(
                f"SELECT COALESCE(SUM(CASE WHEN tipo_movimento='credito' THEN minutos ELSE -minutos END), 0) FROM ponto_banco_horas WHERE colaborador_id = {p};",
                (int(colaborador_id),),
            )
            saldo_ant = int(cur.fetchone()[0] or 0)
            delta = mins if tm == "credito" else -mins
            saldo_novo = saldo_ant + delta
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sql_pg = f"""
                INSERT INTO ponto_banco_horas (
                    empresa_id, colaborador_id, competencia, data_referencia, tipo_movimento,
                    minutos, saldo_acumulado_min, prazo_compensacao, observacao, criado_por, criado_em
                ) VALUES ({','.join([p]*11)}) RETURNING id;
            """
            sql_sq = f"""
                INSERT INTO ponto_banco_horas (
                    empresa_id, colaborador_id, competencia, data_referencia, tipo_movimento,
                    minutos, saldo_acumulado_min, prazo_compensacao, observacao, criado_por, criado_em
                ) VALUES ({','.join([p]*11)});
            """
            bh_id = insert_returning_id(
                cur, conn, sql_pg, sql_sq,
                (emp_id, int(colaborador_id), dt_str[:7], dt_str, tm, mins, saldo_novo, prazo, observacao, usuario, agora),
                self.db_path,
            )
            conn.commit()
        finally:
            conn.close()
        return {"sucesso": True, "movimento_id": bh_id, "saldo_anterior_min": saldo_ant, "saldo_atual_min": saldo_novo, "prazo_compensacao": prazo}

    def obter_saldo_banco_horas(self, colaborador_id: int, empresa_id: Optional[str] = None) -> Dict[str, Any]:
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            self._buscar_colab(cur, int(colaborador_id), empresa_id=empresa_id)
            cur.execute(f"SELECT * FROM ponto_banco_horas WHERE colaborador_id = {p} ORDER BY id DESC LIMIT 100;", (int(colaborador_id),))
            movs = fetchall_dict(cur, self.db_path)
            saldo = sum(int(m["minutos"]) if m["tipo_movimento"] == "credito" else -int(m["minutos"]) for m in movs)
            return {"colaborador_id": int(colaborador_id), "saldo_minutos": saldo, "saldo_horas": round(saldo / 60.0, 2), "movimentos": movs}
        finally:
            conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # RF027 / RF028 / RF029 / RF030 / RF036 / RF037 / RF041..RF050: Espelho Real + Memória
    # ─────────────────────────────────────────────────────────────────────────
    def obter_espelho_ponto(
        self,
        colaborador_id: int,
        mes_ano: str,
        empresa_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """RF027/RF037/RF041-RF050: Apuração diária/mensal real considerando escala, feriados, tolerância CLT art. 58 §1º, HE, noturno e DSR."""
        comp = str(mes_ano or datetime.now().strftime("%Y-%m")).strip()[:7]
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            colab = self._buscar_colab(cur, int(colaborador_id), empresa_id=empresa_id)
            emp_id = colab.get("empresa_id") or "a0000000-0000-0000-0000-000000000001"

            escala = None
            if colab.get("escala_id"):
                cur.execute(f"SELECT * FROM escalas_jornada WHERE id = {p};", (int(colab["escala_id"]),))
                escala = fetchone_dict(cur, self.db_path)
            if not escala:
                cur.execute(f"SELECT * FROM escalas_jornada WHERE empresa_id = {p} AND ativo = 1 ORDER BY id ASC LIMIT 1;", (emp_id,))
                escala = fetchone_dict(cur, self.db_path)

            cur.execute(
                f"SELECT * FROM marcacoes_ponto WHERE colaborador_id = {p} AND data LIKE {p} ORDER BY data ASC, id ASC;",
                (int(colaborador_id), f"{comp}%"),
            )
            marcacoes = fetchall_dict(cur, self.db_path)

            cur.execute(
                f"SELECT * FROM ocorrencias_ponto WHERE colaborador_id = {p} AND (data_inicio LIKE {p} OR data_fim LIKE {p}) ORDER BY data_inicio ASC;",
                (int(colaborador_id), f"{comp}%", f"{comp}%"),
            )
            ocorrencias = fetchall_dict(cur, self.db_path)

            cur.execute(
                f"SELECT * FROM ajustes_ponto WHERE colaborador_id = {p} AND data LIKE {p} ORDER BY data ASC;",
                (int(colaborador_id), f"{comp}%"),
            )
            ajustes = fetchall_dict(cur, self.db_path)

            cur.execute(
                f"SELECT * FROM fechamentos_ponto WHERE empresa_id = {p} AND competencia = {p} ORDER BY id DESC LIMIT 1;",
                (emp_id, comp),
            )
            fechamento = fetchone_dict(cur, self.db_path)

            cur.execute(
                f"SELECT * FROM ponto_historico_jornada WHERE colaborador_id = {p} AND competencia = {p} ORDER BY id DESC LIMIT 100;",
                (int(colaborador_id), comp),
            )
            historico_jornada = fetchall_dict(cur, self.db_path)

            cur.execute(
                f"SELECT COALESCE(SUM(CASE WHEN tipo_movimento='credito' THEN minutos ELSE -minutos END), 0) FROM ponto_banco_horas WHERE colaborador_id = {p};",
                (int(colaborador_id),),
            )
            banco_saldo_min = int(cur.fetchone()[0] or 0)
        finally:
            conn.close()

        tab_srv = TabelasLegaisService(db_path=self.db_path)
        ano_i = int(comp.split("-")[0])
        feriados_map = {
            f["data_feriado"][:10]: f["descricao"]
            for f in tab_srv.listar_feriados(empresa_id=emp_id, ano=ano_i)
            if f["data_feriado"].startswith(comp)
        }
        cal_comp = tab_srv.contar_dias_uteis_dsr_competencia(comp, emp_id)

        # Carga contratual da escala
        ent_esc = _hora_para_min((escala or {}).get("entrada_padrao") or "08:00") or 480
        sai_esc = _hora_para_min((escala or {}).get("saida_padrao") or "17:48") or 1068
        int_esc = int((escala or {}).get("intervalo_minutos") or 60)
        if sai_esc <= ent_esc:
            sai_esc += 1440
        meta_dia_min = max(60, (sai_esc - ent_esc) - int_esc)
        regime = str((escala or {}).get("tipo_regime") or "5x2").lower()

        # Agrupar marcações por dia
        dias_map: Dict[str, List[Dict[str, Any]]] = {}
        for m in marcacoes:
            dias_map.setdefault(m["data"], []).append(m)

        # Ocorrências por dia
        oc_por_dia: Dict[str, List[Dict[str, Any]]] = {}
        for oc in ocorrencias:
            di = datetime.strptime(oc["data_inicio"][:10], "%Y-%m-%d").date()
            df = datetime.strptime(oc["data_fim"][:10], "%Y-%m-%d").date()
            cur_d = di
            while cur_d <= df:
                iso = cur_d.isoformat()
                if iso.startswith(comp):
                    oc_por_dia.setdefault(iso, []).append(oc)
                cur_d += timedelta(days=1)

        grade_dias: List[Dict[str, Any]] = []
        tot_trab_min = 0
        tot_normais_min = 0
        tot_he50_min = 0
        tot_he100_min = 0
        tot_feriado_min = 0
        tot_noturno_min = 0
        tot_prorrog_not_min = 0
        tot_sobreaviso_min = 0
        tot_atraso_min = 0
        tot_saida_ant_min = 0
        tot_faltas_injust_dias = 0
        semanas_com_falta = set()
        ultima_saida_abs_min: Optional[int] = None

        todas_datas = sorted(set(dias_map.keys()) | set(oc_por_dia.keys()))
        for dt_iso in todas_datas:
            dt_obj = datetime.strptime(dt_iso, "%Y-%m-%d").date()
            dia_sem = DIAS_SEMANA_PT[dt_obj.weekday()]
            eh_domingo = dt_obj.weekday() == 6
            eh_sabado_nao_util = (dt_obj.weekday() == 5 and "5x2" in regime)
            eh_feriado = dt_iso in feriados_map
            dia_descanso = eh_domingo or eh_feriado or eh_sabado_nao_util
            meta_hoje = 0 if dia_descanso else meta_dia_min

            regs = _ordenar_marcacoes_dia(dias_map.get(dt_iso, []))
            bats_hhmm = [r["hora"][:5] for r in regs]
            mins_bats = [m for m in (_hora_para_min(b) for b in bats_hhmm) if m is not None]

            # Calcular intervalos entre pares (E1-S1, E2-S2, ...)
            trab_min_dia = 0
            not_min_dia = 0
            prorrog_min_dia = 0
            intrajornada_real = 0
            pares = len(mins_bats) // 2
            for idx_p in range(pares):
                e_m = mins_bats[idx_p * 2]
                s_m = mins_bats[idx_p * 2 + 1]
                if s_m < e_m:
                    s_m += 1440
                trab_min_dia += (s_m - e_m)
                n_m, p_m = _minutos_intervalo_noturno(e_m, s_m)
                not_min_dia += n_m
                prorrog_min_dia += p_m
                if idx_p > 0:
                    prev_s = mins_bats[(idx_p - 1) * 2 + 1]
                    intrajornada_real += max(0, e_m - prev_s)

            # Interjornada CLT art. 66 (11h = 660 min)
            interjornada_violada = False
            interjornada_horas = 11.0
            day_epoch_min = int((dt_obj - date(1970, 1, 1)).days) * 1440
            if mins_bats:
                if ultima_saida_abs_min is not None:
                    diff_inter = (day_epoch_min + mins_bats[0]) - ultima_saida_abs_min
                    interjornada_horas = round(diff_inter / 60.0, 2)
                    if diff_inter < 660:
                        interjornada_violada = True
                ultima_s = mins_bats[-1]
                if len(mins_bats) >= 2 and ultima_s < mins_bats[-2]:
                    ultima_s += 1440
                ultima_saida_abs_min = day_epoch_min + ultima_s

            # Intrajornada CLT art. 71 (>6h exige >= 60 min quando houver >= 2 batidas)
            intrajornada_violada = bool(trab_min_dia > 360 and (len(mins_bats) < 4 or intrajornada_real < min(60, int_esc)))

            # Tolerância CLT art. 58 §1º (5 min por batida, 10 min total diário)
            atraso_dia = 0
            saida_ant_dia = 0
            he_dia_bruto = 0
            if meta_hoje > 0 and mins_bats:
                # Verifica tolerância individual na 1ª entrada e última saída + saldo
                delta_total = trab_min_dia - meta_hoje
                if abs(delta_total) <= 10:
                    delta_efetivo = 0
                else:
                    delta_efetivo = delta_total
                if delta_efetivo > 0:
                    he_dia_bruto = delta_efetivo
                elif delta_efetivo < 0:
                    atraso_ent = max(0, mins_bats[0] - ent_esc)
                    ant_sai = max(0, sai_esc - mins_bats[-1])
                    if atraso_ent > 5:
                        atraso_dia = min(abs(delta_efetivo), atraso_ent)
                    rem_neg = abs(delta_efetivo) - atraso_dia
                    if rem_neg > 0:
                        if ant_sai > 5:
                            saida_ant_dia = rem_neg
                        else:
                            atraso_dia += rem_neg
            elif dia_descanso and trab_min_dia > 0:
                he_dia_bruto = trab_min_dia

            # Ocorrências manuais registradas para este dia
            ocs_d = oc_por_dia.get(dt_iso, [])
            for oc in ocs_d:
                to = str(oc["tipo_ocorrencia"]).lower()
                if to == "falta_injustificada" and str(oc.get("status", "aprovado")) == "aprovado":
                    tot_faltas_injust_dias += 1
                    semanas_com_falta.add(dt_obj.isocalendar()[1])
                elif to == "atraso" and str(oc.get("status", "aprovado")) == "aprovado":
                    atraso_dia += int(oc.get("minutos") or oc.get("minutos_ausencia") or 0)
                elif to == "saida_antecipada" and str(oc.get("status", "aprovado")) == "aprovado":
                    saida_ant_dia += int(oc.get("minutos") or oc.get("minutos_ausencia") or 0)
                elif to == "sobreaviso" and str(oc.get("status", "aprovado")) == "aprovado":
                    tot_sobreaviso_min += int(oc.get("minutos") or oc.get("minutos_ausencia") or 0)

            feriado_min_dia = he_dia_bruto if eh_feriado else 0
            he100_min_dia = he_dia_bruto if (eh_domingo and not eh_feriado) else 0
            he50_min_dia = he_dia_bruto if (not eh_feriado and not eh_domingo) else 0
            normais_min_dia = min(trab_min_dia, meta_hoje) if meta_hoje > 0 else 0

            tot_trab_min += trab_min_dia
            tot_normais_min += normais_min_dia
            tot_he50_min += he50_min_dia
            tot_he100_min += he100_min_dia
            tot_feriado_min += feriado_min_dia
            tot_noturno_min += not_min_dia
            tot_prorrog_not_min += prorrog_min_dia
            tot_atraso_min += atraso_dia
            tot_saida_ant_min += saida_ant_dia

            grade_dias.append({
                "data": dt_iso,
                "dia_semana": f"{dia_sem}{' (Feriado: ' + feriados_map[dt_iso] + ')' if eh_feriado else ''}",
                "batidas": bats_hhmm,
                "origens": [r.get("tipo_registro") for r in regs],
                "horas_trabalhadas": round(trab_min_dia / 60.0, 2),
                "horas_normais": round(normais_min_dia / 60.0, 2),
                "he_50": round(he50_min_dia / 60.0, 2),
                "he_100": round(he100_min_dia / 60.0, 2),
                "horas_feriado": round(feriado_min_dia / 60.0, 2),
                "horas_noturnas": round(not_min_dia / 60.0, 2),
                "prorrogacao_noturna": round(prorrog_min_dia / 60.0, 2),
                "atraso_min": atraso_dia,
                "saida_antecipada_min": saida_ant_dia,
                "saldo_diario_horas": round((he50_min_dia + he100_min_dia + feriado_min_dia - atraso_dia - saida_ant_dia) / 60.0, 2),
                "intrajornada_violada": intrajornada_violada,
                "intervalo_real_min": intrajornada_real,
                "interjornada_violada": interjornada_violada,
                "interjornada_horas": interjornada_horas,
                "limite_2h_extras_excedido": he_dia_bruto > 120,
                "he_total_dia": round(he_dia_bruto / 60.0, 2),
                "ocorrencias_dia": [o["tipo_ocorrencia"] for o in ocs_d],
            })

        # Adicionais horários com hora ficta 52m30s + cálculos financeiros com memória
        sb = float(colab.get("salario_base") or 0.0)
        div_h = float((escala or {}).get("divisor_mensal") or colab.get("carga_horaria_mensal") or 220.0)
        vh_norm = Decimal(str(sb)) / Decimal(str(div_h)) if div_h > 0 else Decimal("0.00")

        he50_h = round(tot_he50_min / 60.0, 2)
        he100_h = round(tot_he100_min / 60.0, 2)
        fer_h = round(tot_feriado_min / 60.0, 2)
        not_h = round(tot_noturno_min / 60.0, 2)
        prorrog_h = round(tot_prorrog_not_min / 60.0, 2)
        sobreav_h = round(tot_sobreaviso_min / 60.0, 2)
        not_fictas_h = round(not_h * (60.0 / 52.5), 2)

        val_he50, _, mem_he50 = calcular_horas_extras(vh_norm, he50_h, 50.0)
        val_he100, _, mem_he100 = calcular_horas_extras(vh_norm, he100_h, 100.0)
        val_fer, _, mem_fer = calcular_trabalho_feriado(vh_norm, fer_h, 100.0)
        val_not, _, mem_not = calcular_adicional_noturno(vh_norm, not_h, 20.0, True, 1.142857)
        val_pror, _, mem_pror = calcular_prorrogacao_noturna(vh_norm, prorrog_h, 20.0, True, 1.142857)
        val_sob, _, mem_sob = calcular_sobreaviso(vh_norm, sobreav_h)

        base_dsr_var = val_he50 + val_he100 + val_fer + val_not + val_pror
        val_dsr_var, mem_dsr = calcular_dsr_sobre_variaveis(base_dsr_var, cal_comp["dias_uteis"], cal_comp["domingos_feriados"])

        # Perda de DSR por falta injustificada (Lei 605/1949 art. 6º)
        dias_dsr_perdidos = len(semanas_com_falta)
        val_dsr_desc = arredondar_moeda((Decimal(str(sb)) / Decimal("30.0")) * Decimal(str(dias_dsr_perdidos))) if dias_dsr_perdidos > 0 else Decimal("0.00")

        memoria_calculo = {
            "competencia": comp,
            "escala": (escala or {}).get("descricao") or "Padrão 220h",
            "calendario": cal_comp,
            "regras_aplicadas": [
                "Tolerância CLT art. 58 §1º (5 min por marcação / 10 min diários)",
                "Hora ficta noturna 52m30s (fator 1.142857 — CLT art. 73 §1º)",
                "Prorrogação de jornada noturna pós-05h (Súmula 60 II TST)",
                "Reflexo DSR Lei 605/1949 sobre variáveis e perda por faltas semanais",
            ],
            "linhas": [mem_he50, mem_he100, mem_fer, mem_not, mem_pror, mem_sob, mem_dsr],
        }

        return {
            "colaborador": {
                "id": colab["id"],
                "nome_completo": colab["nome_completo"],
                "matricula": colab["matricula"],
                "cargo": colab["cargo"],
                "setor": colab["setor"],
                "salario_base": sb,
                "escala": (escala or {}).get("descricao") or colab.get("jornada_trabalho"),
            },
            "periodo": comp,
            "dias_trabalhados": sum(1 for d in grade_dias if d["horas_trabalhadas"] > 0),
            "total_marcacoes": len(marcacoes),
            "grade_dias": grade_dias,
            "ocorrencias": ocorrencias,
            "ajustes": ajustes,
            "fechamento": fechamento,
            "historico_jornada": historico_jornada,
            "banco_horas_saldo_min": banco_saldo_min,
            "totais": {
                "horas_trabalhadas": round(tot_trab_min / 60.0, 2),
                "horas_normais": round(tot_normais_min / 60.0, 2),
                "he_50_horas": he50_h,
                "he_100_horas": he100_h,
                "feriado_100_horas": fer_h,
                "noturno_horas": not_h,
                "noturno_horas_fictas": not_fictas_h,
                "prorrogacao_noturna_horas": prorrog_h,
                "sobreaviso_horas": sobreav_h,
                "atrasos_horas": round(tot_atraso_min / 60.0, 2),
                "saidas_antecipadas_horas": round(tot_saida_ant_min / 60.0, 2),
                "faltas_injustificadas_dias": tot_faltas_injust_dias,
                "dsr_perdidos_dias": dias_dsr_perdidos,
                "valor_he_50": float(val_he50),
                "valor_he_100": float(val_he100),
                "valor_feriado_100": float(val_fer),
                "valor_adicional_noturno": float(val_not),
                "valor_prorrogacao_noturna": float(val_pror),
                "valor_sobreaviso": float(val_sob),
                "valor_dsr_variaveis": float(val_dsr_var),
                "valor_desconto_dsr_faltas": float(val_dsr_desc),
            },
            "memoria_calculo": memoria_calculo,
        }

    def exportar_espelho_ponto_csv(self, colaborador_id: int, mes_ano: str, empresa_id: Optional[str] = None) -> str:
        esp = self.obter_espelho_ponto(colaborador_id, mes_ano, empresa_id=empresa_id)
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(["Colaborador", esp["colaborador"]["nome_completo"], "Matrícula", esp["colaborador"]["matricula"], "Competência", esp["periodo"]])
        w.writerow(["Data", "Dia Semana", "Batidas", "Horas Trab", "HE 50%", "HE 100%", "Feriado 100%", "Noturno", "Atraso (min)", "Saída Ant (min)", "Saldo (h)"])
        for d in esp["grade_dias"]:
            w.writerow([
                d["data"], d["dia_semana"], " | ".join(d["batidas"]), d["horas_trabalhadas"],
                d["he_50"], d["he_100"], d["horas_feriado"], d["horas_noturnas"],
                d["atraso_min"], d["saida_antecipada_min"], d["saldo_diario_horas"],
            ])
        return buf.getvalue()

    def fechar_ponto_periodo(
        self,
        competencia: str,
        usuario: str = "DP / Gestor",
        empresa_id: str = "a0000000-0000-0000-0000-000000000001",
        filial_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """RF028: Fecha o período de ponto da competência bloqueando edições/marcações retroativas."""
        comp = str(competencia or "").strip()[:7]
        if not re.match(r"^\d{4}-\d{2}$", comp):
            raise PlataformaValidacaoException("Competência inválida para fechamento de ponto (use AAAA-MM).")

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(
                f"SELECT id FROM fechamentos_ponto WHERE empresa_id = {p} AND competencia = {p} AND situacao = 'fechado';",
                (empresa_id, comp),
            )
            if cur.fetchone():
                raise PlataformaValidacaoException(f"O ponto da competência {comp} já encontra-se fechado.")

            cur.execute(
                f"SELECT id FROM colaboradores WHERE COALESCE(empresa_id, 'a0000000-0000-0000-0000-000000000001') = {p} AND situacao = 'ativo';",
                (empresa_id,),
            )
            ids_col = [int(r[0]) for r in cur.fetchall()]
        finally:
            conn.close()

        resumos = []
        for cid in ids_col:
            esp = self.obter_espelho_ponto(cid, comp, empresa_id=empresa_id)
            resumos.append({"colaborador_id": cid, "totais": esp["totais"]})

        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            sql_pg = f"""
                INSERT INTO fechamentos_ponto (
                    empresa_id, filial_id, competencia, fechado_em, fechado_por, situacao, resumo_json
                ) VALUES ({p},{p},{p},{p},{p},'fechado',{p}) RETURNING id;
            """
            sql_sq = f"""
                INSERT INTO fechamentos_ponto (
                    empresa_id, filial_id, competencia, fechado_em, fechado_por, situacao, resumo_json
                ) VALUES ({p},{p},{p},{p},{p},'fechado',{p});
            """
            fech_id = insert_returning_id(
                cur, conn, sql_pg, sql_sq,
                (empresa_id, filial_id, comp, agora, usuario, json.dumps(resumos, ensure_ascii=False)),
                self.db_path,
            )
            conn.commit()
        finally:
            conn.close()

        self._auditar(
            modulo="Ponto",
            operacao="fechamento_ponto",
            registro_tipo="fechamentos_ponto",
            registro_id=fech_id,
            usuario=usuario,
            valor_novo=f"fechado ({comp}, {len(resumos)} colaboradores)",
            empresa_id=empresa_id,
        )
        return {"sucesso": True, "fechamento_id": fech_id, "competencia": comp, "situacao": "fechado", "colaboradores_apurados": len(resumos)}

    def reabrir_ponto_periodo(
        self,
        competencia: str,
        justificativa: str,
        usuario: str = "Administrador DP",
        empresa_id: str = "a0000000-0000-0000-0000-000000000001",
    ) -> Dict[str, Any]:
        """RF029: Reabre período fechado mediante autorização e justificativa obrigatória auditada."""
        comp = str(competencia or "").strip()[:7]
        just = str(justificativa or "").strip()
        if not just:
            raise PlataformaValidacaoException("Justificativa obrigatória para reabertura de ponto fechado (RF029).")

        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            cur.execute(
                f"SELECT * FROM fechamentos_ponto WHERE empresa_id = {p} AND competencia = {p} AND situacao = 'fechado' ORDER BY id DESC LIMIT 1;",
                (empresa_id, comp),
            )
            fech = fetchone_dict(cur, self.db_path)
            if not fech:
                raise PlataformaRecursoNaoEncontradoException(f"Nenhum fechamento ativo encontrado para a competência {comp}.")

            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute(
                f"""
                UPDATE fechamentos_ponto
                SET situacao = 'reaberto', justificativa_reabertura = {p}, reaberto_por = {p}, reaberto_em = {p}
                WHERE id = {p};
            """,
                (just, usuario, agora, fech["id"]),
            )
            conn.commit()
        finally:
            conn.close()

        self._auditar(
            modulo="Ponto",
            operacao="reabertura_ponto",
            registro_tipo="fechamentos_ponto",
            registro_id=fech["id"],
            usuario=usuario,
            valor_anterior="fechado",
            valor_novo="reaberto",
            detalhes=just,
            empresa_id=empresa_id,
        )
        return {"sucesso": True, "fechamento_id": fech["id"], "competencia": comp, "situacao": "reaberto", "reaberto_por": usuario}

    # ─────────────────────────────────────────────────────────────────────────
    # RF038 / RF040: Relatórios de Ausências e Absenteísmo Setorial
    # ─────────────────────────────────────────────────────────────────────────
    def relatorio_ausencias(
        self,
        empresa_id: str = "a0000000-0000-0000-0000-000000000001",
        competencia: Optional[str] = None,
        setor: Optional[str] = None,
        colaborador_id: Optional[int] = None,
        tipo: Optional[str] = None,
    ) -> Dict[str, Any]:
        """RF040 / RF038: Gera relatório analítico de ausências, impacto DSR/férias e alertas de absenteísmo setorial."""
        itens = self.listar_ocorrencias(
            empresa_id=empresa_id, colaborador_id=colaborador_id, competencia=competencia, tipo=tipo, setor=setor
        )
        por_setor: Dict[str, Dict[str, Any]] = {}
        por_tipo: Dict[str, int] = {}
        for it in itens:
            st = it.get("setor") or "Sem Setor"
            tp = it.get("tipo_ocorrencia") or "outros"
            por_tipo[tp] = por_tipo.get(tp, 0) + 1
            sec = por_setor.setdefault(st, {"setor": st, "ocorrencias": 0, "minutos_ausencia": 0, "faltas_injustificadas": 0})
            sec["ocorrencias"] += 1
            sec["minutos_ausencia"] += int(it.get("minutos") or it.get("minutos_ausencia") or 0)
            if tp == "falta_injustificada":
                sec["faltas_injustificadas"] += 1

        alertas_setor = [s for s in por_setor.values() if s["faltas_injustificadas"] >= 3 or s["minutos_ausencia"] >= 1440]

        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(["Colaborador", "Matrícula", "Setor", "Data Início", "Data Fim", "Tipo", "Minutos", "Impacta DSR", "Status", "Justificativa"])
        for it in itens:
            w.writerow([
                it.get("colaborador_nome"), it.get("colaborador_matricula"), it.get("setor"),
                it.get("data_inicio"), it.get("data_fim"), it.get("tipo_ocorrencia"),
                it.get("minutos") or it.get("minutos_ausencia") or 0,
                "Sim" if it.get("impacta_dsr") else "Não", it.get("status"), it.get("justificativa"),
            ])

        return {
            "sucesso": True,
            "total_ocorrencias": len(itens),
            "por_tipo": por_tipo,
            "por_setor": list(por_setor.values()),
            "alertas_absenteismo_elevado": alertas_setor,
            "itens": itens,
            "csv": buf.getvalue(),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # RF041..RF050: Eventos de Ponto & Médias Variáveis para Folha / Férias / 13º
    # ─────────────────────────────────────────────────────────────────────────
    def calcular_medias_variaveis_colaborador(
        self,
        colaborador_id: int,
        ano: Optional[int] = None,
        ultimos_meses: int = 12,
    ) -> Dict[str, Any]:
        """RF048/RF049/RF050: Apura médias reais de variáveis (HE, adicionais, comissões) de folha_itens com memória de cálculo."""
        conn = self._conn()
        try:
            cur = conn.cursor()
            p = self._p()
            codigos_variaveis = ("0010", "0011", "0012", "0013", "0015", "0016", "0020", "0021", "0022", "0025", "0030", "0031", "0050", "0051", "101", "102", "103", "105")
            marks = ",".join([p] * len(codigos_variaveis))
            sql = f"""
                SELECT f.competencia, fi.codigo_evento, fi.descricao, fi.valor_total
                FROM folha_itens fi
                JOIN folhas_pagamento f ON f.id = fi.folha_id
                WHERE f.colaborador_id = {p}
                  AND f.situacao IN ('calculada', 'fechada', 'aprovada')
                  AND COALESCE(f.tipo_folha, 'mensal') IN ('mensal', 'complementar')
                  AND fi.tipo = 'provento'
                  AND fi.codigo_evento IN ({marks})
            """
            params: List[Any] = [int(colaborador_id), *codigos_variaveis]
            if ano:
                sql += f" AND f.competencia LIKE {p}"
                params.append(f"{int(ano)}-%")
            sql += " ORDER BY f.competencia DESC;"
            cur.execute(sql, tuple(params))
            linhas = fetchall_dict(cur, self.db_path)
        finally:
            conn.close()

        competencias_dist = sorted({ln["competencia"] for ln in linhas}, reverse=True)[:max(1, int(ultimos_meses))]
        linhas_filt = [ln for ln in linhas if ln["competencia"] in competencias_dist]
        soma_var = sum(Decimal(str(ln["valor_total"] or 0)) for ln in linhas_filt)
        divisor = Decimal(str(len(competencias_dist))) if competencias_dist else Decimal("12")
        media_mensal = arredondar_moeda(soma_var / divisor) if linhas_filt else Decimal("0.00")

        mem = (
            f"Média de variáveis ({len(competencias_dist)} competência(s) apurada(s)): "
            f"Soma R$ {soma_var:,.2f} / {divisor} = R$ {media_mensal:,.2f}"
        ).replace(".", ",")
        return {
            "colaborador_id": int(colaborador_id),
            "competencias_consideradas": competencias_dist,
            "total_variaveis_apurado": float(arredondar_moeda(soma_var)),
            "divisor_meses": int(divisor),
            "media_mensal": float(media_mensal),
            "memoria_calculo": mem,
        }

    def gerar_eventos_folha_do_ponto(
        self,
        colaborador_id: int,
        competencia: str,
        empresa_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Converte apuração real do espelho/ocorrências do ponto em eventos prontos para FolhaService."""
        esp = self.obter_espelho_ponto(colaborador_id, competencia, empresa_id=empresa_id)
        t = esp["totais"]
        evs: List[Dict[str, Any]] = []
        if t["he_50_horas"] > 0:
            evs.append({"codigo": "0010", "referencia": t["he_50_horas"], "percentual": 50.0})
        if t["he_100_horas"] > 0:
            evs.append({"codigo": "0011", "referencia": t["he_100_horas"], "percentual": 100.0})
        if t["feriado_100_horas"] > 0:
            evs.append({"codigo": "0013", "referencia": t["feriado_100_horas"], "percentual": 100.0})
        if t["noturno_horas"] > 0:
            evs.append({"codigo": "0020", "referencia": t["noturno_horas"], "percentual": 20.0})
        if t["prorrogacao_noturna_horas"] > 0:
            evs.append({"codigo": "0022", "referencia": t["prorrogacao_noturna_horas"], "percentual": 20.0})
        if t["sobreaviso_horas"] > 0:
            evs.append({"codigo": "0025", "referencia": t["sobreaviso_horas"]})
        if t["faltas_injustificadas_dias"] > 0:
            evs.append({"codigo": "0530", "referencia": t["faltas_injustificadas_dias"]})
        if t["dsr_perdidos_dias"] > 0:
            evs.append({"codigo": "0531", "referencia": t["dsr_perdidos_dias"]})
        atraso_tot = round(t["atrasos_horas"] + t["saidas_antecipadas_horas"], 2)
        if atraso_tot > 0:
            evs.append({"codigo": "0532", "referencia": atraso_tot})
        return evs
