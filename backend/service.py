"""
Camada de Servicos de Negocio — Colaboradores (RF-001 a RF-010)
Contem a logica de aplicacao, gestao de dependentes, historico funcional imutavel,
anexos seguros e versionados, controle de documentacao/vencimentos, dados bancarios,
auditoria cadastral unificada, validacoes de duplicidade e persistencia dual SQLite/PostgreSQL.
"""
import base64
import hashlib
import json
import os
import re
import tempfile
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from .database import _usar_postgres, fetchall_dict, fetchone_dict, get_connection, init_db, insert_returning_id, ph
from .validators import (
    converter_para_data,
    formatar_cpf,
    normalizar_cpf,
    validar_arquivo_documento,
    validar_dados_bancarios,
    validar_dependente,
    validar_formulario_colaborador,
)

CAMPOS_COMPARAVEIS = [
    ("nome_completo",   "Nome Completo"),
    ("cpf",             "CPF"),
    ("rg",              "RG"),
    ("data_nascimento", "Data de Nascimento"),
    ("telefone",        "Telefone"),
    ("email",           "E-mail"),
    ("logradouro",      "Logradouro"),
    ("numero",          "Numero"),
    ("bairro",          "Bairro"),
    ("cidade",          "Cidade"),
    ("uf",              "UF"),
    ("cep",             "CEP"),
    ("matricula",       "Matricula"),
    ("data_admissao",   "Data de Admissao"),
    ("cargo",           "Cargo"),
    ("setor",           "Setor"),
    ("departamento",    "Departamento"),
    ("centro_custo",    "Centro de Custo"),
    ("tipo_contrato",   "Tipo de Contrato"),
    ("jornada_trabalho", "Jornada de Trabalho"),
    ("carga_horaria_mensal", "Carga Horária Mensal"),
    ("pis_pasep",       "PIS/PASEP/NIT"),
    ("sexo",            "Sexo"),
    ("estado_civil",    "Estado Civil"),
    ("salario_base",    "Salário-base"),
    ("situacao",        "Situação do Vínculo"),
]

TIPOS_MOVIMENTACAO_VALIDOS = {
    "admissao",
    "promocao",
    "transferencia",
    "reajuste_salarial",
    "mudanca_cargo",
    "mudanca_setor",
    "alteracao_jornada",
    "alteracao_centro_custo",
    "outra_movimentacao",
}


class ValidacaoException(Exception):
    def __init__(self, erros: dict):
        super().__init__("Erros de validacao encontrados.")
        self.erros = erros


class RecursoNaoEncontradoException(Exception):
    pass


class ColaboradorService:
    def __init__(self, db_path: str = None):
        self.db_path = db_path
        init_db(self.db_path)

    # ──────────────────────────────────────────────────────────
    # Shortcut helpers
    # ──────────────────────────────────────────────────────────

    def _ph(self) -> str:
        return ph(self.db_path)

    def _pg(self) -> bool:
        return _usar_postgres(self.db_path)

    def _conn(self):
        return get_connection(self.db_path)

    def _fetchone(self, cursor):
        return fetchone_dict(cursor, self.db_path)

    def _fetchall(self, cursor):
        return fetchall_dict(cursor, self.db_path)

    def _insert_id(self, cursor, conn, sql_pg, sql_sqlite, params):
        return insert_returning_id(cursor, conn, sql_pg, sql_sqlite, params, self.db_path)

    def _storage_dir(self) -> str:
        if os.environ.get("PRIVATE_DOCS_DIR"):
            base = os.environ["PRIVATE_DOCS_DIR"]
        elif os.environ.get("VERCEL"):
            base = os.path.join(tempfile.gettempdir(), "rh20_private_docs")
        elif self.db_path and str(self.db_path) != ":memory:":
            base = os.path.join(os.path.dirname(os.path.abspath(self.db_path)), "rh20_private_docs")
        else:
            base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "storage", "private_docs"))
        os.makedirs(base, exist_ok=True)
        return base

    _COLUNA_CACHE = {}

    def _tabela_tem_coluna(self, cursor, tabela: str, coluna: str) -> bool:
        """Verifica de forma resiliente e com cache em memória se a tabela possui a coluna informada."""
        chave = (self.db_path or "__default__", tabela, coluna)
        if chave in self._COLUNA_CACHE:
            return self._COLUNA_CACHE[chave]
        try:
            if self._pg():
                cursor.execute(
                    "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
                    (tabela, coluna)
                )
                existe = cursor.fetchone() is not None
            else:
                cursor.execute(f"PRAGMA table_info({tabela})")
                cols = [row[1] if isinstance(row, (tuple, list)) else row["name"] for row in cursor.fetchall()]
                existe = coluna in cols
            self._COLUNA_CACHE[chave] = existe
            return existe
        except Exception:
            return False

    # ──────────────────────────────────────────────────────────
    # RF-010: Helper Unificado de Auditoria Cadastral
    # ──────────────────────────────────────────────────────────

    def _registrar_auditoria_cadastral(
        self,
        cursor,
        colaborador_id: int,
        empresa_id: str,
        entidade: str,
        operacao: str,
        campo_alterado: str,
        valor_anterior: Any,
        valor_novo: Any,
        usuario: str,
        origem: str = "API",
        ip_origem: Optional[str] = None,
        justificativa: Optional[str] = None,
        agora: Optional[str] = None,
    ):
        """Grava rastreabilidade cadastral em historico_alteracoes e espelha em auditoria_operacoes na mesma transação."""
        P = self._ph()
        ts = agora or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        v_ant = None if valor_anterior is None else str(valor_anterior)
        v_nov = None if valor_novo is None else str(valor_novo)
        cursor.execute(f"""
            INSERT INTO historico_alteracoes (
                colaborador_id, data_hora, entidade, operacao, campo_alterado,
                valor_anterior, valor_novo, usuario_responsavel, origem, ip_origem, justificativa
            ) VALUES ({P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P})
        """, (
            colaborador_id, ts, entidade, operacao, campo_alterado,
            v_ant, v_nov, usuario or "Sistema/Administrador", origem or "API", ip_origem, justificativa or ""
        ))
        try:
            det = f"[{entidade}] {campo_alterado}: {v_ant or '-'} -> {v_nov or '-'}"
            if justificativa:
                det += f" | Justificativa: {justificativa}"
            cursor.execute(f"""
                INSERT INTO auditoria_operacoes (
                    empresa_id, modulo, operacao, registro_tipo, registro_id,
                    campo_alterado, valor_anterior, valor_novo, usuario_responsavel,
                    ip_origem, detalhes, criado_em
                ) VALUES ({P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P})
            """, (
                empresa_id or "a0000000-0000-0000-0000-000000000001",
                "Colaboradores",
                operacao,
                entidade,
                f"colaborador:{colaborador_id}",
                campo_alterado,
                v_ant,
                v_nov,
                usuario or "Sistema/Administrador",
                ip_origem,
                det,
                ts,
            ))
        except Exception:
            pass

    def _inserir_movimentacao_funcional_cursor(
        self,
        cursor,
        conn,
        colaborador_id: int,
        empresa_id: str,
        tipo_movimentacao: str,
        campo_afetado: str,
        valor_anterior: Any,
        valor_novo: Any,
        data_alteracao: str,
        data_vigencia: str,
        justificativa: str,
        observacoes: str,
        usuario: str,
        origem: str = "API",
        ip_origem: Optional[str] = None,
        criado_em: Optional[str] = None,
    ) -> int:
        P = self._ph()
        ts = criado_em or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        retroativa = 1 if (data_vigencia and data_alteracao and data_vigencia < data_alteracao) else 0
        sql_pg = f"""
            INSERT INTO historico_funcional (
                colaborador_id, empresa_id, tipo_movimentacao, campo_afetado,
                valor_anterior, valor_novo, data_alteracao, data_vigencia, retroativa,
                justificativa, observacoes, usuario_responsavel, origem, ip_origem, criado_em
            ) VALUES ({P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P}) RETURNING id
        """
        sql_sqlite = f"""
            INSERT INTO historico_funcional (
                colaborador_id, empresa_id, tipo_movimentacao, campo_afetado,
                valor_anterior, valor_novo, data_alteracao, data_vigencia, retroativa,
                justificativa, observacoes, usuario_responsavel, origem, ip_origem, criado_em
            ) VALUES ({P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P})
        """
        return self._insert_id(cursor, conn, sql_pg, sql_sqlite, (
            colaborador_id,
            empresa_id or "a0000000-0000-0000-0000-000000000001",
            tipo_movimentacao,
            campo_afetado,
            None if valor_anterior is None else str(valor_anterior),
            str(valor_novo),
            data_alteracao,
            data_vigencia,
            retroativa,
            justificativa or "",
            observacoes or "",
            usuario or "Sistema/Administrador",
            origem or "API",
            ip_origem,
            ts,
        ))

    # ──────────────────────────────────────────────────────────
    # CRUD Colaboradores (RF-001 a RF-004 + Integração RF-005/006/010)
    # ──────────────────────────────────────────────────────────

    def gerar_proxima_matricula(self) -> str:
        """Gera uma matrícula única sequencial no padrão RH-XXXX."""
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute("SELECT matricula FROM colaboradores;")
        existentes = {str(r[0]).strip().upper() for r in cursor.fetchall() if r and r[0]}
        conn.close()
        seq = 1001 + len(existentes)
        while f"RH-{seq}" in existentes:
            seq += 1
        return f"RH-{seq}"

    def cadastrar(
        self,
        dados: dict,
        usuario: str = "Sistema/Administrador",
        origem: str = "API",
        ip_origem: Optional[str] = None,
    ) -> dict:
        """Cadastra um novo colaborador com validacao, dependentes, admissao funcional e auditoria."""
        dados_proc = dict(dados or {})
        if dados_proc.get("auto_gerar_matricula") and not (dados_proc.get("matricula") or "").strip():
            dados_proc["matricula"] = self.gerar_proxima_matricula()

        is_valido, erros, sanitizado = validar_formulario_colaborador(dados_proc, is_edicao=False)
        if not is_valido:
            raise ValidacaoException(erros)

        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()

        cursor.execute(f"SELECT id FROM colaboradores WHERE cpf = {P}", (sanitizado["cpf"],))
        if cursor.fetchone():
            conn.close()
            raise ValidacaoException({"cpf": f"Ja existe um colaborador com o CPF {sanitizado['cpf']}."})

        cursor.execute(f"SELECT id FROM colaboradores WHERE matricula = {P}", (sanitizado["matricula"],))
        if cursor.fetchone():
            conn.close()
            raise ValidacaoException({"matricula": f"Ja existe um colaborador com a matricula {sanitizado['matricula']}."})

        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        hoje_str = agora[:10]
        empresa_id = (dados_proc.get("empresa_id") or "a0000000-0000-0000-0000-000000000001").strip()

        sql_pg = """
            INSERT INTO colaboradores (
                empresa_id, matricula, nome_completo, cpf, rg, data_nascimento,
                telefone, email, logradouro, numero, bairro, cidade, uf, cep,
                data_admissao, cargo, setor, departamento, centro_custo,
                tipo_contrato, jornada_trabalho, carga_horaria_mensal,
                pis_pasep, sexo, estado_civil,
                salario_base, situacao, criado_em, atualizado_em
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """
        sql_sqlite = """
            INSERT INTO colaboradores (
                empresa_id, matricula, nome_completo, cpf, rg, data_nascimento,
                telefone, email, logradouro, numero, bairro, cidade, uf, cep,
                data_admissao, cargo, setor, departamento, centro_custo,
                tipo_contrato, jornada_trabalho, carga_horaria_mensal,
                pis_pasep, sexo, estado_civil,
                salario_base, situacao, criado_em, atualizado_em
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """
        params = (
            empresa_id,
            sanitizado["matricula"],
            sanitizado["nome_completo"],
            sanitizado["cpf"],
            sanitizado.get("rg", ""),
            sanitizado["data_nascimento"],
            sanitizado.get("telefone", ""),
            sanitizado["email"],
            sanitizado.get("logradouro", ""),
            sanitizado.get("numero", ""),
            sanitizado.get("bairro", ""),
            sanitizado.get("cidade", ""),
            sanitizado.get("uf", ""),
            sanitizado.get("cep", ""),
            sanitizado["data_admissao"],
            sanitizado["cargo"],
            sanitizado["setor"],
            sanitizado.get("departamento", sanitizado["setor"]),
            sanitizado.get("centro_custo", ""),
            sanitizado.get("tipo_contrato", "CLT"),
            sanitizado.get("jornada_trabalho", "44h semanais"),
            sanitizado.get("carga_horaria_mensal", 220.0),
            sanitizado.get("pis_pasep", ""),
            sanitizado.get("sexo", ""),
            sanitizado.get("estado_civil", ""),
            sanitizado["salario_base"],
            sanitizado.get("situacao", "ativo"),
            agora,
            agora,
        )

        colaborador_id = self._insert_id(cursor, conn, sql_pg, sql_sqlite, params)

        for dep in sanitizado.get("dependentes", []):
            cursor.execute(f"""
                INSERT INTO dependentes (
                    colaborador_id, nome, cpf, parentesco, tipo_dependencia,
                    data_nascimento, eh_dependente_irrf, eh_elegivel_salario_familia,
                    eh_plano_saude, situacao, data_inclusao, data_encerramento,
                    observacoes, criado_em, atualizado_em
                ) VALUES ({P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P})
            """, (
                colaborador_id, dep["nome"], dep.get("cpf", ""), dep["parentesco"],
                dep.get("tipo_dependencia", "legal"), dep.get("data_nascimento", ""),
                int(dep.get("eh_dependente_irrf", 1)), int(dep.get("eh_elegivel_salario_familia", 0)),
                int(dep.get("eh_plano_saude", 0)), dep.get("situacao", "ativo"),
                dep.get("data_inclusao") or hoje_str, dep.get("data_encerramento") or None,
                dep.get("observacoes", ""), agora, agora,
            ))

        # RF-006: Registro inicial de Admissão no Histórico Funcional
        self._inserir_movimentacao_funcional_cursor(
            cursor, conn, colaborador_id, empresa_id,
            tipo_movimentacao="admissao",
            campo_afetado="Admissão",
            valor_anterior=None,
            valor_novo=f"Cargo: {sanitizado['cargo']} | Setor: {sanitizado['setor']} | Salário: R$ {sanitizado['salario_base']:.2f} | Jornada: {sanitizado.get('jornada_trabalho', '44h semanais')}",
            data_alteracao=hoje_str,
            data_vigencia=sanitizado["data_admissao"],
            justificativa="Admissão inicial do colaborador",
            observacoes="",
            usuario=usuario,
            origem=origem,
            ip_origem=ip_origem,
            criado_em=agora,
        )

        # RF-010: Auditoria Cadastral
        self._registrar_auditoria_cadastral(
            cursor, colaborador_id, empresa_id,
            entidade="colaborador", operacao="inclusao",
            campo_alterado="Criacao de Cadastro",
            valor_anterior=None,
            valor_novo=f"Colaborador {sanitizado['nome_completo']} admitido com matricula {sanitizado['matricula']}.",
            usuario=usuario, origem=origem, ip_origem=ip_origem, agora=agora,
        )

        conn.commit()
        conn.close()
        return self.obter_por_id(colaborador_id)

    def listar(
        self,
        termo: str = None,
        situacao: str = None,
        setor: str = None,
        cargo: str = None,
        nome: str = None,
        matricula: str = None,
        cpf: str = None,
        empresa_id: str = None,
    ) -> list:
        """Lista colaboradores com pesquisa e filtros por nome, matrícula, CPF, cargo, setor e empresa."""
        P = self._ph()
        pg = self._pg()

        conn = self._conn()
        cursor = conn.cursor()

        sql = """
            SELECT c.*, COUNT(CASE WHEN d.id IS NOT NULL AND COALESCE(d.situacao, 'ativo') = 'ativo' THEN 1 END) AS total_dependentes
            FROM colaboradores c
            LEFT JOIN dependentes d ON d.colaborador_id = c.id
            WHERE 1=1
        """
        params = []

        tem_empresa_col = self._tabela_tem_coluna(cursor, "colaboradores", "empresa_id")
        if empresa_id and empresa_id.strip() and tem_empresa_col:
            sql += f" AND (c.empresa_id = {P} OR c.empresa_id IS NULL)"
            params.append(empresa_id.strip())

        if situacao and situacao.lower() in ("ativo", "inativo", "afastado", "ferias", "desligado"):
            sql += f" AND c.situacao = {P}"
            params.append(situacao.lower())

        if setor and setor.strip():
            padrao_setor = f"%{setor.strip()}%"
            sql += f" AND c.setor ILIKE {P}" if pg else f" AND LOWER(c.setor) LIKE LOWER({P})"
            params.append(padrao_setor)

        if cargo and cargo.strip():
            padrao_cargo = f"%{cargo.strip()}%"
            sql += f" AND c.cargo ILIKE {P}" if pg else f" AND LOWER(c.cargo) LIKE LOWER({P})"
            params.append(padrao_cargo)

        if nome and nome.strip():
            padrao_nome = f"%{nome.strip()}%"
            sql += f" AND c.nome_completo ILIKE {P}" if pg else f" AND LOWER(c.nome_completo) LIKE LOWER({P})"
            params.append(padrao_nome)

        if matricula and matricula.strip():
            padrao_mat = f"%{matricula.strip()}%"
            sql += f" AND c.matricula ILIKE {P}" if pg else f" AND LOWER(c.matricula) LIKE LOWER({P})"
            params.append(padrao_mat)

        if cpf and cpf.strip():
            cpf_limpo = cpf.strip()
            cpf_dig = normalizar_cpf(cpf_limpo)
            padrao_cpf_raw = f"%{cpf_limpo}%"
            padrao_cpf_dig = f"%{cpf_dig}%" if cpf_dig else ""
            if pg:
                sql += f" AND (c.cpf ILIKE {P} OR ({P} != '' AND REPLACE(REPLACE(c.cpf, '.', ''), '-', '') ILIKE {P}))"
            else:
                sql += f" AND (c.cpf LIKE {P} OR ({P} != '' AND REPLACE(REPLACE(c.cpf, '.', ''), '-', '') LIKE {P}))"
            params.extend([padrao_cpf_raw, cpf_dig, padrao_cpf_dig])

        if termo and termo.strip():
            termo_limpo = termo.strip()
            cpf_digitos = normalizar_cpf(termo_limpo)
            padrao = f"%{termo_limpo}%"
            padrao_cpf = f"%{cpf_digitos}%" if cpf_digitos else ""

            if pg:
                sql += f""" AND (
                    c.nome_completo ILIKE {P} OR
                    c.matricula     ILIKE {P} OR
                    c.cpf           ILIKE {P} OR
                    ({P} != '' AND REPLACE(REPLACE(c.cpf, '.', ''), '-', '') ILIKE {P}) OR
                    c.cargo         ILIKE {P} OR
                    c.setor         ILIKE {P}
                )"""
            else:
                sql += f""" AND (
                    LOWER(c.nome_completo) LIKE LOWER({P}) OR
                    LOWER(c.matricula) LIKE LOWER({P}) OR
                    c.cpf LIKE {P} OR
                    ({P} != '' AND REPLACE(REPLACE(c.cpf, '.', ''), '-', '') LIKE {P}) OR
                    LOWER(c.cargo) LIKE LOWER({P}) OR
                    LOWER(c.setor) LIKE LOWER({P})
                )"""
            params.extend([padrao, padrao, padrao, cpf_digitos, padrao_cpf, padrao, padrao])

        sql += " GROUP BY c.id ORDER BY c.nome_completo ASC"

        cursor.execute(sql, params)
        resultado = self._fetchall(cursor)
        conn.close()

        for r in resultado:
            if r.get("salario_base") is not None:
                r["salario_base"] = float(r["salario_base"])
        return resultado

    def obter_por_id(self, colaborador_id: int, empresa_id: str = None) -> dict:
        """Retorna dados completos do colaborador, dependentes, documentos, dados bancarios e historico."""
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()

        sql = f"SELECT * FROM colaboradores WHERE id = {P}"
        params = [colaborador_id]
        if empresa_id and empresa_id.strip() and self._tabela_tem_coluna(cursor, "colaboradores", "empresa_id"):
            sql += f" AND (empresa_id = {P} OR empresa_id IS NULL)"
            params.append(empresa_id.strip())

        cursor.execute(sql, tuple(params))
        colab = self._fetchone(cursor)
        if not colab:
            conn.close()
            raise RecursoNaoEncontradoException(f"Colaborador com ID {colaborador_id} nao encontrado ou acesso nao autorizado.")

        cursor.execute(
            f"""SELECT id, nome, cpf, parentesco,
                       COALESCE(tipo_dependencia, 'legal') AS tipo_dependencia,
                       COALESCE(data_nascimento, '') AS data_nascimento,
                       COALESCE(eh_dependente_irrf, 1) AS eh_dependente_irrf,
                       COALESCE(eh_elegivel_salario_familia, 0) AS eh_elegivel_salario_familia,
                       COALESCE(eh_plano_saude, 0) AS eh_plano_saude,
                       COALESCE(situacao, 'ativo') AS situacao,
                       COALESCE(data_inclusao, '') AS data_inclusao,
                       COALESCE(data_encerramento, '') AS data_encerramento,
                       COALESCE(observacoes, '') AS observacoes
                FROM dependentes
                WHERE colaborador_id = {P} AND COALESCE(situacao, 'ativo') = 'ativo'
                ORDER BY id ASC""",
            (colaborador_id,)
        )
        colab["dependentes"] = self._fetchall(cursor)

        try:
            cursor.execute(
                f"""SELECT id, tipo_documento, COALESCE(categoria, tipo_documento) AS categoria,
                           nome_arquivo, mime_type, tamanho_bytes, observacao,
                           data_emissao, data_validade, COALESCE(situacao, 'ativo') AS situacao,
                           COALESCE(versao, 1) AS versao, documento_raiz_id,
                           enviado_por, criado_em
                    FROM colaborador_documentos
                    WHERE colaborador_id = {P} AND COALESCE(situacao, 'ativo') = 'ativo'
                    ORDER BY id DESC""",
                (colaborador_id,)
            )
            colab["documentos"] = self._fetchall(cursor)
        except Exception:
            colab["documentos"] = []

        try:
            cursor.execute(
                f"""SELECT id, colaborador_id, tipo_movimentacao, campo_afetado, valor_anterior, valor_novo,
                           data_alteracao, data_vigencia, retroativa, justificativa, observacoes,
                           usuario_responsavel, origem, criado_em
                    FROM historico_funcional
                    WHERE colaborador_id = {P}
                    ORDER BY data_vigencia DESC, id DESC""",
                (colaborador_id,)
            )
            colab["historico_funcional"] = self._fetchall(cursor)
        except Exception:
            colab["historico_funcional"] = []

        try:
            cursor.execute(
                f"""SELECT id, banco_codigo, banco_nome, agencia, agencia_digito, conta, conta_digito,
                           tipo_conta, chave_pix_tipo, chave_pix, titular_nome, titular_cpf, principal, ativo, criado_em
                    FROM colaborador_dados_bancarios
                    WHERE colaborador_id = {P} AND ativo = 1
                    ORDER BY principal DESC, id DESC""",
                (colaborador_id,)
            )
            colab["dados_bancarios"] = self._fetchall(cursor)
        except Exception:
            colab["dados_bancarios"] = []

        cursor.execute(f"""
            SELECT id, data_hora, COALESCE(entidade, 'colaborador') AS entidade,
                   COALESCE(operacao, 'alteracao') AS operacao, campo_alterado,
                   valor_anterior, valor_novo, usuario_responsavel, origem, ip_origem, justificativa
            FROM historico_alteracoes
            WHERE colaborador_id = {P}
            ORDER BY id DESC
        """, (colaborador_id,))
        colab["historico"] = self._fetchall(cursor)

        conn.close()

        if colab.get("salario_base") is not None:
            colab["salario_base"] = float(colab["salario_base"])
        return colab

    def obter_historico(self, colaborador_id: int) -> list:
        """Retorna a trilha auditada de alteracoes cadastrais do colaborador (RF-003 / RF-010)."""
        colab = self.obter_por_id(colaborador_id)
        return colab.get("historico", [])

    def atualizar(
        self,
        colaborador_id: int,
        dados: dict,
        usuario: str = "Sistema/Administrador",
        justificativa: str = None,
        origem: str = "API",
        ip_origem: Optional[str] = None,
    ) -> dict:
        """Controla e audita alteracoes cadastrais do colaborador na mesma transacao do historico funcional."""
        atual = self.obter_por_id(colaborador_id)
        payload_mesclado = {**atual, **(dados or {})}
        is_valido, erros, sanitizado = validar_formulario_colaborador(payload_mesclado, is_edicao=True)
        if not is_valido:
            raise ValidacaoException(erros)

        motivo_alt = (
            justificativa
            or (dados or {}).get("justificativa")
            or (dados or {}).get("motivo_alteracao")
            or ""
        ).strip()
        responsavel_auditado = f"{usuario} (Justificativa: {motivo_alt})" if motivo_alt else usuario
        data_vig = ((dados or {}).get("data_vigencia") or datetime.now().strftime("%Y-%m-%d")).strip()[:10]

        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()

        cursor.execute(
            f"SELECT id FROM colaboradores WHERE cpf = {P} AND id != {P}",
            (sanitizado["cpf"], colaborador_id)
        )
        if cursor.fetchone():
            conn.close()
            raise ValidacaoException({"cpf": f"O CPF {sanitizado['cpf']} ja pertence a outro colaborador."})

        cursor.execute(
            f"SELECT id FROM colaboradores WHERE matricula = {P} AND id != {P}",
            (sanitizado["matricula"], colaborador_id)
        )
        if cursor.fetchone():
            conn.close()
            raise ValidacaoException({"matricula": f"A matricula {sanitizado['matricula']} ja pertence a outro colaborador."})

        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        hoje_str = agora[:10]
        emp_id = atual.get("empresa_id") or "a0000000-0000-0000-0000-000000000001"

        alteracoes = []
        campos_mudados = {}
        for campo_bd, rotulo in CAMPOS_COMPARAVEIS:
            val_antigo = atual.get(campo_bd)
            val_novo = sanitizado.get(campo_bd)
            str_antigo = "" if val_antigo is None else str(val_antigo).strip()
            str_novo = "" if val_novo is None else str(val_novo).strip()

            if campo_bd == "salario_base" and val_antigo is not None and val_novo is not None:
                if abs(float(val_antigo) - float(val_novo)) > 0.001:
                    ant_fmt = f"R$ {float(val_antigo):.2f}"
                    nov_fmt = f"R$ {float(val_novo):.2f}"
                    alteracoes.append((rotulo, ant_fmt, nov_fmt))
                    campos_mudados[campo_bd] = (float(val_antigo), float(val_novo), ant_fmt, nov_fmt)
            elif str_antigo != str_novo:
                alteracoes.append((rotulo, str_antigo, str_novo))
                campos_mudados[campo_bd] = (str_antigo, str_novo, str_antigo, str_novo)

        cursor.execute(f"""
            UPDATE colaboradores SET
                matricula={P}, nome_completo={P}, cpf={P}, rg={P},
                data_nascimento={P}, telefone={P}, email={P},
                logradouro={P}, numero={P}, bairro={P}, cidade={P},
                uf={P}, cep={P}, data_admissao={P}, cargo={P},
                setor={P}, departamento={P}, centro_custo={P},
                tipo_contrato={P}, jornada_trabalho={P}, carga_horaria_mensal={P},
                pis_pasep={P}, sexo={P}, estado_civil={P},
                salario_base={P}, situacao={P}, atualizado_em={P}
            WHERE id={P}
        """, (
            sanitizado["matricula"], sanitizado["nome_completo"],
            sanitizado["cpf"], sanitizado.get("rg", ""),
            sanitizado["data_nascimento"], sanitizado.get("telefone", ""),
            sanitizado["email"], sanitizado.get("logradouro", ""),
            sanitizado.get("numero", ""), sanitizado.get("bairro", ""),
            sanitizado.get("cidade", ""), sanitizado.get("uf", ""),
            sanitizado.get("cep", ""), sanitizado["data_admissao"],
            sanitizado["cargo"], sanitizado["setor"],
            sanitizado.get("departamento", sanitizado["setor"]),
            sanitizado.get("centro_custo", ""),
            sanitizado.get("tipo_contrato", "CLT"),
            sanitizado.get("jornada_trabalho", "44h semanais"),
            sanitizado.get("carga_horaria_mensal", 220.0),
            sanitizado.get("pis_pasep", ""),
            sanitizado.get("sexo", ""),
            sanitizado.get("estado_civil", ""),
            sanitizado["salario_base"], sanitizado.get("situacao", atual["situacao"]),
            agora, colaborador_id,
        ))

        # RF-006: Grava movimentações funcionais na mesma transação quando houver mudança funcional
        mudou_cargo = "cargo" in campos_mudados
        mudou_sal = "salario_base" in campos_mudados
        if mudou_cargo and mudou_sal and float(campos_mudados["salario_base"][1]) > float(campos_mudados["salario_base"][0]):
            self._inserir_movimentacao_funcional_cursor(
                cursor, conn, colaborador_id, emp_id,
                tipo_movimentacao="promocao",
                campo_afetado="Cargo e Salário-base",
                valor_anterior=f"{campos_mudados['cargo'][2]} | {campos_mudados['salario_base'][2]}",
                valor_novo=f"{campos_mudados['cargo'][3]} | {campos_mudados['salario_base'][3]}",
                data_alteracao=hoje_str, data_vigencia=data_vig,
                justificativa=motivo_alt or "Promoção funcional",
                observacoes="", usuario=usuario, origem=origem, ip_origem=ip_origem, criado_em=agora,
            )
        else:
            if mudou_cargo:
                self._inserir_movimentacao_funcional_cursor(
                    cursor, conn, colaborador_id, emp_id,
                    tipo_movimentacao="mudanca_cargo", campo_afetado="Cargo",
                    valor_anterior=campos_mudados["cargo"][2], valor_novo=campos_mudados["cargo"][3],
                    data_alteracao=hoje_str, data_vigencia=data_vig,
                    justificativa=motivo_alt or "Alteração de cargo",
                    observacoes="", usuario=usuario, origem=origem, ip_origem=ip_origem, criado_em=agora,
                )
            if mudou_sal:
                self._inserir_movimentacao_funcional_cursor(
                    cursor, conn, colaborador_id, emp_id,
                    tipo_movimentacao="reajuste_salarial", campo_afetado="Salário-base",
                    valor_anterior=campos_mudados["salario_base"][2], valor_novo=campos_mudados["salario_base"][3],
                    data_alteracao=hoje_str, data_vigencia=data_vig,
                    justificativa=motivo_alt or "Reajuste salarial",
                    observacoes="", usuario=usuario, origem=origem, ip_origem=ip_origem, criado_em=agora,
                )

        if "setor" in campos_mudados or "departamento" in campos_mudados:
            ref_s = campos_mudados.get("setor") or campos_mudados.get("departamento")
            self._inserir_movimentacao_funcional_cursor(
                cursor, conn, colaborador_id, emp_id,
                tipo_movimentacao="mudanca_setor", campo_afetado="Setor / Departamento",
                valor_anterior=ref_s[2], valor_novo=ref_s[3],
                data_alteracao=hoje_str, data_vigencia=data_vig,
                justificativa=motivo_alt or "Transferência / mudança de setor",
                observacoes="", usuario=usuario, origem=origem, ip_origem=ip_origem, criado_em=agora,
            )
        if "jornada_trabalho" in campos_mudados or "carga_horaria_mensal" in campos_mudados:
            ant_j = f"{atual.get('jornada_trabalho', '')} ({atual.get('carga_horaria_mensal', '')}h)"
            nov_j = f"{sanitizado.get('jornada_trabalho', '')} ({sanitizado.get('carga_horaria_mensal', '')}h)"
            self._inserir_movimentacao_funcional_cursor(
                cursor, conn, colaborador_id, emp_id,
                tipo_movimentacao="alteracao_jornada", campo_afetado="Jornada de Trabalho",
                valor_anterior=ant_j, valor_novo=nov_j,
                data_alteracao=hoje_str, data_vigencia=data_vig,
                justificativa=motivo_alt or "Alteração de jornada",
                observacoes="", usuario=usuario, origem=origem, ip_origem=ip_origem, criado_em=agora,
            )
        if "centro_custo" in campos_mudados:
            self._inserir_movimentacao_funcional_cursor(
                cursor, conn, colaborador_id, emp_id,
                tipo_movimentacao="alteracao_centro_custo", campo_afetado="Centro de Custo",
                valor_anterior=campos_mudados["centro_custo"][2], valor_novo=campos_mudados["centro_custo"][3],
                data_alteracao=hoje_str, data_vigencia=data_vig,
                justificativa=motivo_alt or "Alteração de centro de custo",
                observacoes="", usuario=usuario, origem=origem, ip_origem=ip_origem, criado_em=agora,
            )

        # Preserva dependentes inativos existentes ao atualizar lista inline de dependentes ativos
        deps_antigos = atual.get("dependentes", [])
        deps_novos = sanitizado.get("dependentes", [])
        if "dependentes" in (dados or {}):
            cursor.execute(
                f"DELETE FROM dependentes WHERE colaborador_id = {P} AND COALESCE(situacao, 'ativo') = 'ativo'",
                (colaborador_id,)
            )
            for dep in deps_novos:
                cursor.execute(f"""
                    INSERT INTO dependentes (
                        colaborador_id, nome, cpf, parentesco, tipo_dependencia,
                        data_nascimento, eh_dependente_irrf, eh_elegivel_salario_familia,
                        eh_plano_saude, situacao, data_inclusao, data_encerramento,
                        observacoes, criado_em, atualizado_em
                    ) VALUES ({P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P})
                """, (
                    colaborador_id, dep["nome"], dep.get("cpf", ""), dep["parentesco"],
                    dep.get("tipo_dependencia", "legal"), dep.get("data_nascimento", ""),
                    int(dep.get("eh_dependente_irrf", 1)), int(dep.get("eh_elegivel_salario_familia", 0)),
                    int(dep.get("eh_plano_saude", 0)), "ativo",
                    dep.get("data_inclusao") or hoje_str, None,
                    dep.get("observacoes", ""), agora, agora,
                ))

            if (len(deps_antigos) != len(deps_novos) or
                    json.dumps(deps_antigos, sort_keys=True) != json.dumps(deps_novos, sort_keys=True)):
                alteracoes.append((
                    "Dependentes",
                    f"{len(deps_antigos)} dependente(s)",
                    f"{len(deps_novos)} dependente(s)",
                ))

        for campo, antigo, novo in alteracoes:
            self._registrar_auditoria_cadastral(
                cursor, colaborador_id, emp_id,
                entidade="colaborador", operacao="alteracao",
                campo_alterado=campo, valor_anterior=antigo, valor_novo=novo,
                usuario=responsavel_auditado, origem=origem, ip_origem=ip_origem,
                justificativa=motivo_alt, agora=agora,
            )

        conn.commit()
        conn.close()
        return self.obter_por_id(colaborador_id)

    def inativar(
        self,
        colaborador_id: int,
        motivo: str = None,
        usuario: str = "Sistema/Administrador",
        origem: str = "API",
        ip_origem: Optional[str] = None,
    ) -> dict:
        """Inativacao logica sem excluir historico ou dados."""
        atual = self.obter_por_id(colaborador_id)
        if atual["situacao"] == "inativo":
            return atual

        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        emp_id = atual.get("empresa_id") or "a0000000-0000-0000-0000-000000000001"

        cursor.execute(f"UPDATE colaboradores SET situacao='inativo', atualizado_em={P} WHERE id={P}", (agora, colaborador_id))
        desc_motivo = f" (Motivo: {motivo})" if motivo and motivo.strip() else ""
        self._registrar_auditoria_cadastral(
            cursor, colaborador_id, emp_id,
            entidade="colaborador", operacao="inativacao",
            campo_alterado="Situação do Vínculo",
            valor_anterior=atual["situacao"], valor_novo=f"inativo{desc_motivo}",
            usuario=usuario, origem=origem, ip_origem=ip_origem,
            justificativa=(motivo or "").strip(), agora=agora,
        )

        conn.commit()
        conn.close()
        return self.obter_por_id(colaborador_id)

    def reativar(
        self,
        colaborador_id: int,
        usuario: str = "Sistema/Administrador",
        origem: str = "API",
        ip_origem: Optional[str] = None,
    ) -> dict:
        """Reativacao logica com auditoria."""
        atual = self.obter_por_id(colaborador_id)
        if atual["situacao"] == "ativo":
            return atual

        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        emp_id = atual.get("empresa_id") or "a0000000-0000-0000-0000-000000000001"

        cursor.execute(f"UPDATE colaboradores SET situacao='ativo', atualizado_em={P} WHERE id={P}", (agora, colaborador_id))
        self._registrar_auditoria_cadastral(
            cursor, colaborador_id, emp_id,
            entidade="colaborador", operacao="reativacao",
            campo_alterado="Situação do Vínculo",
            valor_anterior=atual["situacao"], valor_novo="ativo",
            usuario=usuario, origem=origem, ip_origem=ip_origem, agora=agora,
        )

        conn.commit()
        conn.close()
        return self.obter_por_id(colaborador_id)

    # ──────────────────────────────────────────────────────────
    # RF-005: Gestão Completa de Dependentes
    # ──────────────────────────────────────────────────────────

    def listar_dependentes(self, colaborador_id: int, incluir_inativos: bool = False, empresa_id: str = None) -> list:
        self.obter_por_id(colaborador_id, empresa_id=empresa_id)
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        sql = f"""
            SELECT id, colaborador_id, nome, cpf, parentesco,
                   COALESCE(tipo_dependencia, 'legal') AS tipo_dependencia,
                   COALESCE(data_nascimento, '') AS data_nascimento,
                   COALESCE(eh_dependente_irrf, 1) AS eh_dependente_irrf,
                   COALESCE(eh_elegivel_salario_familia, 0) AS eh_elegivel_salario_familia,
                   COALESCE(eh_plano_saude, 0) AS eh_plano_saude,
                   COALESCE(situacao, 'ativo') AS situacao,
                   COALESCE(data_inclusao, '') AS data_inclusao,
                   COALESCE(data_encerramento, '') AS data_encerramento,
                   COALESCE(observacoes, '') AS observacoes,
                   criado_em, atualizado_em
            FROM dependentes
            WHERE colaborador_id = {P}
        """
        if not incluir_inativos:
            sql += " AND COALESCE(situacao, 'ativo') = 'ativo'"
        sql += " ORDER BY id ASC"
        cursor.execute(sql, (colaborador_id,))
        rows = self._fetchall(cursor)
        conn.close()
        return rows

    def cadastrar_dependente(
        self,
        colaborador_id: int,
        dados: dict,
        usuario: str = "Sistema/Administrador",
        origem: str = "API",
        ip_origem: Optional[str] = None,
        empresa_id: str = None,
    ) -> dict:
        colab = self.obter_por_id(colaborador_id, empresa_id=empresa_id)
        ok, erros_lista = validar_dependente(dados or {}, exigir_campos_completos=True)
        if not ok:
            raise ValidacaoException({"dependente": " ".join(erros_lista)})

        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        emp_id = colab.get("empresa_id") or "a0000000-0000-0000-0000-000000000001"

        nome = (dados.get("nome") or "").strip()
        cpf_norm = normalizar_cpf(dados.get("cpf") or "")
        cpf_fmt = formatar_cpf(cpf_norm) if cpf_norm else ""
        dt_nasc_obj = converter_para_data(dados.get("data_nascimento"))
        dt_nasc = dt_nasc_obj.strftime("%Y-%m-%d") if dt_nasc_obj else ""
        dt_inc_obj = converter_para_data(dados.get("data_inclusao")) if dados.get("data_inclusao") else None
        dt_inc = dt_inc_obj.strftime("%Y-%m-%d") if dt_inc_obj else agora[:10]
        dt_enc_obj = converter_para_data(dados.get("data_encerramento")) if dados.get("data_encerramento") else None
        dt_enc = dt_enc_obj.strftime("%Y-%m-%d") if dt_enc_obj else None

        # Prevenir duplicidade ativa por CPF ou (nome + data_nascimento)
        if cpf_fmt:
            cursor.execute(
                f"SELECT id FROM dependentes WHERE colaborador_id = {P} AND cpf = {P} AND COALESCE(situacao, 'ativo') = 'ativo'",
                (colaborador_id, cpf_fmt),
            )
            if cursor.fetchone():
                conn.close()
                raise ValidacaoException({"cpf": f"Já existe dependente ativo com o CPF {cpf_fmt} neste colaborador."})
        cursor.execute(
            f"SELECT id FROM dependentes WHERE colaborador_id = {P} AND LOWER(nome) = LOWER({P}) AND COALESCE(data_nascimento, '') = {P} AND COALESCE(situacao, 'ativo') = 'ativo'",
            (colaborador_id, nome, dt_nasc),
        )
        if cursor.fetchone():
            conn.close()
            raise ValidacaoException({"nome": f"Dependente '{nome}' já cadastrado e ativo para este colaborador."})

        eh_irrf = 1 if dados.get("eh_dependente_irrf", 1) in (1, True, "1", "true", "True") else 0
        eh_sf = 1 if dados.get("eh_elegivel_salario_familia", 0) in (1, True, "1", "true", "True") else 0
        eh_saude = 1 if dados.get("eh_plano_saude", 0) in (1, True, "1", "true", "True") else 0
        tipo_dep = (dados.get("tipo_dependencia") or "legal").strip()
        parentesco = (dados.get("parentesco") or "").strip()
        obs = (dados.get("observacoes") or "").strip()

        sql_pg = f"""
            INSERT INTO dependentes (
                colaborador_id, nome, cpf, parentesco, tipo_dependencia, data_nascimento,
                eh_dependente_irrf, eh_elegivel_salario_familia, eh_plano_saude,
                situacao, data_inclusao, data_encerramento, observacoes, criado_em, atualizado_em
            ) VALUES ({P},{P},{P},{P},{P},{P},{P},{P},{P},'ativo',{P},{P},{P},{P},{P}) RETURNING id
        """
        sql_sqlite = f"""
            INSERT INTO dependentes (
                colaborador_id, nome, cpf, parentesco, tipo_dependencia, data_nascimento,
                eh_dependente_irrf, eh_elegivel_salario_familia, eh_plano_saude,
                situacao, data_inclusao, data_encerramento, observacoes, criado_em, atualizado_em
            ) VALUES ({P},{P},{P},{P},{P},{P},{P},{P},{P},'ativo',{P},{P},{P},{P},{P})
        """
        dep_id = self._insert_id(cursor, conn, sql_pg, sql_sqlite, (
            colaborador_id, nome, cpf_fmt, parentesco, tipo_dep, dt_nasc,
            eh_irrf, eh_sf, eh_saude, dt_inc, dt_enc, obs, agora, agora
        ))

        self._registrar_auditoria_cadastral(
            cursor, colaborador_id, emp_id,
            entidade="dependente", operacao="inclusao",
            campo_alterado="Dependente Cadastrado",
            valor_anterior=None,
            valor_novo=f"{nome} ({parentesco}) | IRRF={eh_irrf}, SalFam={eh_sf}, Saúde={eh_saude}",
            usuario=usuario, origem=origem, ip_origem=ip_origem, agora=agora,
        )
        conn.commit()
        cursor.execute(f"SELECT * FROM dependentes WHERE id = {P}", (dep_id,))
        row = self._fetchone(cursor)
        conn.close()
        return row

    def editar_dependente(
        self,
        colaborador_id: int,
        dependente_id: int,
        dados: dict,
        usuario: str = "Sistema/Administrador",
        origem: str = "API",
        ip_origem: Optional[str] = None,
        empresa_id: str = None,
    ) -> dict:
        colab = self.obter_por_id(colaborador_id, empresa_id=empresa_id)
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM dependentes WHERE id = {P} AND colaborador_id = {P}", (dependente_id, colaborador_id))
        atual = self._fetchone(cursor)
        if not atual:
            conn.close()
            raise RecursoNaoEncontradoException("Dependente não encontrado para este colaborador.")

        merged = {**atual, **(dados or {})}
        ok, erros_lista = validar_dependente(merged, exigir_campos_completos=True)
        if not ok:
            conn.close()
            raise ValidacaoException({"dependente": " ".join(erros_lista)})

        nome = (merged.get("nome") or "").strip()
        cpf_norm = normalizar_cpf(merged.get("cpf") or "")
        cpf_fmt = formatar_cpf(cpf_norm) if cpf_norm else ""
        dt_nasc = converter_para_data(merged.get("data_nascimento")).strftime("%Y-%m-%d")
        dt_inc = (converter_para_data(merged.get("data_inclusao")).strftime("%Y-%m-%d") if merged.get("data_inclusao") else (atual.get("data_inclusao") or datetime.now().strftime("%Y-%m-%d")))
        dt_enc = converter_para_data(merged.get("data_encerramento")).strftime("%Y-%m-%d") if merged.get("data_encerramento") else None

        if cpf_fmt:
            cursor.execute(
                f"SELECT id FROM dependentes WHERE colaborador_id = {P} AND cpf = {P} AND id != {P} AND COALESCE(situacao, 'ativo') = 'ativo'",
                (colaborador_id, cpf_fmt, dependente_id),
            )
            if cursor.fetchone():
                conn.close()
                raise ValidacaoException({"cpf": f"Já existe outro dependente ativo com CPF {cpf_fmt}."})

        eh_irrf = 1 if merged.get("eh_dependente_irrf", 1) in (1, True, "1", "true", "True") else 0
        eh_sf = 1 if merged.get("eh_elegivel_salario_familia", 0) in (1, True, "1", "true", "True") else 0
        eh_saude = 1 if merged.get("eh_plano_saude", 0) in (1, True, "1", "true", "True") else 0
        tipo_dep = (merged.get("tipo_dependencia") or "legal").strip()
        parentesco = (merged.get("parentesco") or "").strip()
        situacao = str(merged.get("situacao") or "ativo").strip().lower()
        obs = (merged.get("observacoes") or "").strip()
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        emp_id = colab.get("empresa_id") or "a0000000-0000-0000-0000-000000000001"

        cursor.execute(f"""
            UPDATE dependentes SET
                nome={P}, cpf={P}, parentesco={P}, tipo_dependencia={P}, data_nascimento={P},
                eh_dependente_irrf={P}, eh_elegivel_salario_familia={P}, eh_plano_saude={P},
                situacao={P}, data_inclusao={P}, data_encerramento={P}, observacoes={P}, atualizado_em={P}
            WHERE id={P} AND colaborador_id={P}
        """, (
            nome, cpf_fmt, parentesco, tipo_dep, dt_nasc,
            eh_irrf, eh_sf, eh_saude, situacao, dt_inc, dt_enc, obs, agora,
            dependente_id, colaborador_id,
        ))

        self._registrar_auditoria_cadastral(
            cursor, colaborador_id, emp_id,
            entidade="dependente", operacao="alteracao",
            campo_alterado=f"Dependente: {atual['nome']}",
            valor_anterior=f"Parentesco={atual.get('parentesco')} | IRRF={atual.get('eh_dependente_irrf')} | SalFam={atual.get('eh_elegivel_salario_familia')} | Saúde={atual.get('eh_plano_saude', 0)}",
            valor_novo=f"Nome={nome}, Parentesco={parentesco} | IRRF={eh_irrf} | SalFam={eh_sf} | Saúde={eh_saude} | Situação={situacao}",
            usuario=usuario, origem=origem, ip_origem=ip_origem, agora=agora,
        )
        conn.commit()
        cursor.execute(f"SELECT * FROM dependentes WHERE id = {P}", (dependente_id,))
        row = self._fetchone(cursor)
        conn.close()
        return row

    def inativar_dependente(
        self,
        colaborador_id: int,
        dependente_id: int,
        motivo: str = "",
        data_encerramento: Optional[str] = None,
        usuario: str = "Sistema/Administrador",
        origem: str = "API",
        ip_origem: Optional[str] = None,
        empresa_id: str = None,
    ) -> dict:
        colab = self.obter_por_id(colaborador_id, empresa_id=empresa_id)
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM dependentes WHERE id = {P} AND colaborador_id = {P}", (dependente_id, colaborador_id))
        atual = self._fetchone(cursor)
        if not atual:
            conn.close()
            raise RecursoNaoEncontradoException("Dependente não encontrado para este colaborador.")

        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        dt_enc = (converter_para_data(data_encerramento).strftime("%Y-%m-%d") if data_encerramento and converter_para_data(data_encerramento) else agora[:10])
        emp_id = colab.get("empresa_id") or "a0000000-0000-0000-0000-000000000001"

        cursor.execute(f"""
            UPDATE dependentes SET situacao='inativo', data_encerramento={P}, atualizado_em={P}
            WHERE id={P} AND colaborador_id={P}
        """, (dt_enc, agora, dependente_id, colaborador_id))

        self._registrar_auditoria_cadastral(
            cursor, colaborador_id, emp_id,
            entidade="dependente", operacao="inativacao",
            campo_alterado=f"Inativação Dependente: {atual['nome']}",
            valor_anterior="ativo",
            valor_novo=f"inativo (encerrado em {dt_enc})",
            usuario=usuario, origem=origem, ip_origem=ip_origem,
            justificativa=(motivo or "").strip(), agora=agora,
        )
        conn.commit()
        cursor.execute(f"SELECT * FROM dependentes WHERE id = {P}", (dependente_id,))
        row = self._fetchone(cursor)
        conn.close()
        return row

    # ──────────────────────────────────────────────────────────
    # RF-006: Histórico Funcional Imutável e Transacional
    # ──────────────────────────────────────────────────────────

    def listar_historico_funcional(
        self,
        colaborador_id: int,
        tipo_movimentacao: Optional[str] = None,
        data_inicio: Optional[str] = None,
        data_fim: Optional[str] = None,
        empresa_id: str = None,
    ) -> list:
        self.obter_por_id(colaborador_id, empresa_id=empresa_id)
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        sql = f"SELECT * FROM historico_funcional WHERE colaborador_id = {P}"
        params: List[Any] = [colaborador_id]
        if tipo_movimentacao and tipo_movimentacao != "todos":
            sql += f" AND tipo_movimentacao = {P}"
            params.append(tipo_movimentacao.strip().lower())
        if data_inicio:
            sql += f" AND data_vigencia >= {P}"
            params.append(data_inicio.strip()[:10])
        if data_fim:
            sql += f" AND data_vigencia <= {P}"
            params.append(data_fim.strip()[:10])
        sql += " ORDER BY data_vigencia DESC, id DESC"
        cursor.execute(sql, tuple(params))
        rows = self._fetchall(cursor)
        conn.close()
        return rows

    def registrar_movimentacao_funcional(
        self,
        colaborador_id: int,
        dados: dict,
        usuario: str = "Sistema/Administrador",
        origem: str = "API",
        ip_origem: Optional[str] = None,
        empresa_id: str = None,
    ) -> dict:
        """Registra movimentação funcional imutável e, quando aplicável, atualiza o colaborador na mesma transação."""
        atual = self.obter_por_id(colaborador_id, empresa_id=empresa_id)
        tipo = str((dados or {}).get("tipo_movimentacao") or "").strip().lower()
        if tipo not in TIPOS_MOVIMENTACAO_VALIDOS:
            raise ValidacaoException({
                "tipo_movimentacao": f"Tipo de movimentação inválido. Permitidos: {', '.join(sorted(TIPOS_MOVIMENTACAO_VALIDOS))}."
            })
        data_vig_raw = ((dados or {}).get("data_vigencia") or datetime.now().strftime("%Y-%m-%d")).strip()
        dt_vig_obj = converter_para_data(data_vig_raw)
        if not dt_vig_obj:
            raise ValidacaoException({"data_vigencia": "Data de vigência inválida. Use AAAA-MM-DD."})
        data_vig = dt_vig_obj.strftime("%Y-%m-%d")

        justificativa = ((dados or {}).get("justificativa") or (dados or {}).get("motivo") or "").strip()
        if not justificativa:
            raise ValidacaoException({"justificativa": "Justificativa da movimentação funcional é obrigatória."})
        observacoes = ((dados or {}).get("observacoes") or "").strip()

        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        hoje_str = agora[:10]
        emp_id = atual.get("empresa_id") or "a0000000-0000-0000-0000-000000000001"
        aplicar = (dados or {}).get("aplicar_no_cadastro", True) in (True, 1, "1", "true")

        mapa_campo = {
            "promocao": ("cargo", "Cargo (Promoção)"),
            "reajuste_salarial": ("salario_base", "Salário-base"),
            "mudanca_cargo": ("cargo", "Cargo"),
            "transferencia": ("setor", "Transferência / Setor"),
            "mudanca_setor": ("setor", "Setor"),
            "alteracao_jornada": ("jornada_trabalho", "Jornada de Trabalho"),
            "alteracao_centro_custo": ("centro_custo", "Centro de Custo"),
        }

        campos_multi = [
            ("cargo_novo", "cargo", "Cargo"),
            ("setor_novo", "setor", "Setor"),
            ("departamento_novo", "departamento", "Departamento"),
            ("centro_custo_novo", "centro_custo", "Centro de Custo"),
            ("salario_novo", "salario_base", "Salário-base"),
            ("jornada_nova", "jornada_trabalho", "Jornada de Trabalho"),
            ("carga_horaria_nova", "carga_horaria_mensal", "Carga Horária Mensal"),
        ]
        alteracoes_multi = []
        for req_k, col_k, rot_k in campos_multi:
            v_raw = (dados or {}).get(req_k)
            if v_raw is not None and str(v_raw).strip() != "":
                alteracoes_multi.append((col_k, rot_k, v_raw))

        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()

        if alteracoes_multi:
            from .validators import validar_salario_base
            rotulos = []
            antes_list = []
            novos_list = []
            updates_sql = []
            updates_params = []
            setor_informado = any(col_k == "setor" for col_k, _, _ in alteracoes_multi)
            depto_informado = any(col_k == "departamento" for col_k, _, _ in alteracoes_multi)

            for col_k, rot_k, v_raw in alteracoes_multi:
                val_ant = atual.get(col_k)
                if col_k == "salario_base":
                    ok_sal, sal_float, msg_sal = validar_salario_base(v_raw)
                    if not ok_sal:
                        conn.close()
                        raise ValidacaoException({"salario_novo": msg_sal})
                    ant_fmt = f"R$ {float(val_ant):.2f}" if val_ant is not None else "--"
                    nov_fmt = f"R$ {sal_float:.2f}"
                    db_val = sal_float
                elif col_k == "carga_horaria_mensal":
                    try:
                        db_val = int(float(v_raw))
                    except (TypeError, ValueError):
                        conn.close()
                        raise ValidacaoException({"carga_horaria_nova": "Carga horária inválida."})
                    ant_fmt = str(val_ant) if val_ant is not None else "--"
                    nov_fmt = str(db_val)
                else:
                    db_val = str(v_raw).strip()
                    ant_fmt = str(val_ant) if val_ant not in (None, "") else "--"
                    nov_fmt = db_val
                rotulos.append(rot_k)
                antes_list.append(f"{rot_k}: {ant_fmt}" if len(alteracoes_multi) > 1 else ant_fmt)
                novos_list.append(f"{rot_k}: {nov_fmt}" if len(alteracoes_multi) > 1 else nov_fmt)
                updates_sql.append(f"{col_k}={P}")
                updates_params.append(db_val)
                if col_k == "setor" and setor_informado and not depto_informado:
                    updates_sql.append(f"departamento={P}")
                    updates_params.append(db_val)

            if aplicar and updates_sql:
                updates_sql.append(f"atualizado_em={P}")
                updates_params.extend([agora, colaborador_id])
                cursor.execute(f"UPDATE colaboradores SET {', '.join(updates_sql)} WHERE id={P}", tuple(updates_params))

            rotulo_alvo = ", ".join(rotulos)
            valor_anterior = (dados or {}).get("valor_anterior")
            if valor_anterior is None:
                valor_anterior = " | ".join(antes_list)
            valor_novo_str = " | ".join(novos_list)
        else:
            valor_novo_raw = (dados or {}).get("valor_novo")
            if valor_novo_raw is None or str(valor_novo_raw).strip() == "":
                conn.close()
                raise ValidacaoException({"valor_novo": "Informe ao menos um novo valor ou campo alterado para a movimentação."})

            col_alvo, rotulo_alvo = mapa_campo.get(tipo, (None, (dados or {}).get("campo_afetado") or tipo))
            valor_anterior = (dados or {}).get("valor_anterior")
            if valor_anterior is None and col_alvo:
                val_ant = atual.get(col_alvo)
                valor_anterior = f"R$ {float(val_ant):.2f}" if col_alvo == "salario_base" and val_ant is not None else val_ant

            valor_novo_str = str(valor_novo_raw).strip()
            if col_alvo == "salario_base":
                from .validators import validar_salario_base
                ok_sal, sal_float, msg_sal = validar_salario_base(valor_novo_raw)
                if not ok_sal:
                    conn.close()
                    raise ValidacaoException({"valor_novo": msg_sal})
                valor_novo_str = f"R$ {sal_float:.2f}"
                if aplicar:
                    cursor.execute(f"UPDATE colaboradores SET salario_base={P}, atualizado_em={P} WHERE id={P}", (sal_float, agora, colaborador_id))
            elif col_alvo == "setor" and aplicar:
                cursor.execute(f"UPDATE colaboradores SET setor={P}, departamento={P}, atualizado_em={P} WHERE id={P}", (valor_novo_str, valor_novo_str, agora, colaborador_id))
            elif col_alvo and aplicar:
                cursor.execute(f"UPDATE colaboradores SET {col_alvo}={P}, atualizado_em={P} WHERE id={P}", (valor_novo_str, agora, colaborador_id))

        mov_id = self._inserir_movimentacao_funcional_cursor(
            cursor, conn, colaborador_id, emp_id,
            tipo_movimentacao=tipo, campo_afetado=rotulo_alvo,
            valor_anterior=valor_anterior, valor_novo=valor_novo_str,
            data_alteracao=hoje_str, data_vigencia=data_vig,
            justificativa=justificativa, observacoes=observacoes,
            usuario=usuario, origem=origem, ip_origem=ip_origem, criado_em=agora,
        )

        self._registrar_auditoria_cadastral(
            cursor, colaborador_id, emp_id,
            entidade="historico_funcional", operacao="inclusao",
            campo_alterado=f"Movimentação: {rotulo_alvo}",
            valor_anterior=valor_anterior, valor_novo=f"{valor_novo_str} (Vigência: {data_vig})",
            usuario=usuario, origem=origem, ip_origem=ip_origem, justificativa=justificativa, agora=agora,
        )

        conn.commit()
        cursor.execute(f"SELECT * FROM historico_funcional WHERE id = {P}", (mov_id,))
        row = self._fetchone(cursor)
        conn.close()
        return row

    # ──────────────────────────────────────────────────────────
    # RF-007: Anexos Cadastrais Seguros e Versionados
    # ──────────────────────────────────────────────────────────

    def _decodificar_base64(self, conteudo_base64: str) -> bytes:
        raw = (conteudo_base64 or "").strip()
        if not raw:
            return b""
        if "," in raw and raw.startswith("data:"):
            raw = raw.split(",", 1)[1]
        try:
            return base64.b64decode(raw, validate=False)
        except Exception:
            return raw.encode("utf-8", errors="ignore")

    def adicionar_documento(
        self,
        colaborador_id: int,
        tipo_documento: str,
        nome_arquivo: str,
        conteudo_base64: str = "",
        mime_type: str = "application/octet-stream",
        tamanho_bytes: int = 0,
        observacao: str = "",
        usuario: str = "Sistema/Administrador",
        categoria: Optional[str] = None,
        data_emissao: Optional[str] = None,
        data_validade: Optional[str] = None,
        documento_raiz_id: Optional[int] = None,
        empresa_id: Optional[str] = None,
        origem: str = "API",
        ip_origem: Optional[str] = None,
    ) -> dict:
        """Anexa um documento cadastral seguro em armazenamento privado, com versionamento e auditoria (RF-007)."""
        colab = self.obter_por_id(colaborador_id, empresa_id=empresa_id)
        tipo_doc = (tipo_documento or "").strip()
        nome_arq = (nome_arquivo or "").strip()
        if not tipo_doc or not nome_arq:
            raise ValidacaoException({"documento": "Tipo de documento e nome do arquivo são obrigatórios."})

        emp_id = colab.get("empresa_id") or "a0000000-0000-0000-0000-000000000001"
        cfg = self.obter_config_alertas_documentos(empresa_id=emp_id)
        max_mb = int(cfg.get("tamanho_max_mb") or 10)

        file_bytes = self._decodificar_base64(conteudo_base64)
        tam_real = len(file_bytes) if file_bytes else int(tamanho_bytes or 0)
        if tam_real > max_mb * 1024 * 1024:
            raise ValidacaoException({"documento": f"Arquivo excede o limite máximo de {max_mb} MB."})

        ok_arq, msg_arq, mime_validado = validar_arquivo_documento(nome_arq, mime_type, file_bytes, tamanho_max_mb=max_mb)
        if not ok_arq:
            raise ValidacaoException({"documento": msg_arq})

        dt_emi = None
        if data_emissao and str(data_emissao).strip():
            obj = converter_para_data(str(data_emissao).strip())
            if not obj:
                raise ValidacaoException({"data_emissao": "Data de emissão inválida."})
            dt_emi = obj.strftime("%Y-%m-%d")

        dt_val = None
        if data_validade and str(data_validade).strip():
            obj = converter_para_data(str(data_validade).strip())
            if not obj:
                raise ValidacaoException({"data_validade": "Data de validade inválida."})
            if dt_emi and obj.strftime("%Y-%m-%d") < dt_emi:
                raise ValidacaoException({"data_validade": "Data de validade não pode ser anterior à data de emissão."})
            dt_val = obj.strftime("%Y-%m-%d")

        _, ext = os.path.splitext(nome_arq.lower())
        nome_interno = f"{uuid.uuid4().hex}{ext}"
        dir_emp = os.path.join(self._storage_dir(), re.sub(r"[^a-zA-Z0-9_-]", "_", emp_id))
        os.makedirs(dir_emp, exist_ok=True)
        caminho_priv = os.path.join(dir_emp, nome_interno)
        if file_bytes:
            with open(caminho_priv, "wb") as f:
                f.write(file_bytes)
        sha256_hex = hashlib.sha256(file_bytes).hexdigest() if file_bytes else ""

        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cat_final = (categoria or tipo_doc).strip()

        versao = 1
        raiz_id = None
        if documento_raiz_id:
            cursor.execute(
                f"SELECT id, documento_raiz_id, versao FROM colaborador_documentos WHERE id = {P} AND colaborador_id = {P}",
                (int(documento_raiz_id), colaborador_id),
            )
            ref = self._fetchone(cursor)
            if not ref:
                conn.close()
                raise RecursoNaoEncontradoException("Documento base não encontrado para nova versão.")
            raiz_id = int(ref.get("documento_raiz_id") or ref["id"])
            cursor.execute(
                f"SELECT COALESCE(MAX(versao), 1) FROM colaborador_documentos WHERE (id = {P} OR documento_raiz_id = {P}) AND colaborador_id = {P}",
                (raiz_id, raiz_id, colaborador_id),
            )
            versao = int(cursor.fetchone()[0] or 1) + 1
            cursor.execute(
                f"UPDATE colaborador_documentos SET situacao = 'substituido', atualizado_por = {P}, atualizado_em = {P} WHERE (id = {P} OR documento_raiz_id = {P}) AND colaborador_id = {P} AND COALESCE(situacao, 'ativo') = 'ativo'",
                (usuario, agora, raiz_id, raiz_id, colaborador_id),
            )

        sql_pg = f"""
            INSERT INTO colaborador_documentos (
                colaborador_id, empresa_id, tipo_documento, categoria, nome_arquivo,
                nome_interno_seguro, caminho_privado, mime_type, tamanho_bytes, sha256_hash,
                conteudo_base64, observacao, data_emissao, data_validade, situacao, versao,
                documento_raiz_id, enviado_por, criado_em, atualizado_por, atualizado_em
            ) VALUES ({P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},'ativo',{P},{P},{P},{P},{P},{P}) RETURNING id
        """
        sql_sqlite = f"""
            INSERT INTO colaborador_documentos (
                colaborador_id, empresa_id, tipo_documento, categoria, nome_arquivo,
                nome_interno_seguro, caminho_privado, mime_type, tamanho_bytes, sha256_hash,
                conteudo_base64, observacao, data_emissao, data_validade, situacao, versao,
                documento_raiz_id, enviado_por, criado_em, atualizado_por, atualizado_em
            ) VALUES ({P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},'ativo',{P},{P},{P},{P},{P},{P})
        """
        doc_id = self._insert_id(cursor, conn, sql_pg, sql_sqlite, (
            colaborador_id, emp_id, tipo_doc, cat_final, nome_arq,
            nome_interno, caminho_priv, mime_validado, tam_real, sha256_hex,
            "", (observacao or "").strip(), dt_emi, dt_val, versao,
            raiz_id, usuario, agora, usuario, agora,
        ))
        if not raiz_id:
            cursor.execute(f"UPDATE colaborador_documentos SET documento_raiz_id = {P} WHERE id = {P}", (doc_id, doc_id))

        self._registrar_auditoria_cadastral(
            cursor, colaborador_id, emp_id,
            entidade="documento", operacao="nova_versao" if raiz_id else "inclusao",
            campo_alterado="Documento Anexado" if not raiz_id else "Nova Versão de Documento",
            valor_anterior=f"v{versao - 1}" if raiz_id else None,
            valor_novo=f"{cat_final}: {nome_arq} (v{versao})",
            usuario=usuario, origem=origem, ip_origem=ip_origem, agora=agora,
        )

        conn.commit()
        cursor.execute(
            f"""SELECT id, colaborador_id, empresa_id, tipo_documento, categoria, nome_arquivo,
                       nome_interno_seguro, mime_type, tamanho_bytes, sha256_hash, observacao,
                       data_emissao, data_validade, situacao, versao, documento_raiz_id,
                       enviado_por, criado_em
                FROM colaborador_documentos WHERE id = {P}""",
            (doc_id,),
        )
        doc = self._fetchone(cursor)
        conn.close()
        return doc

    def listar_documentos(
        self,
        colaborador_id: int,
        categoria: Optional[str] = None,
        termo: Optional[str] = None,
        incluir_inativos: bool = False,
        empresa_id: str = None,
    ) -> list:
        """Lista os documentos anexados do colaborador com filtros por categoria e pesquisa."""
        self.obter_por_id(colaborador_id, empresa_id=empresa_id)
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        sql = f"""
            SELECT id, colaborador_id, tipo_documento, COALESCE(categoria, tipo_documento) AS categoria,
                   nome_arquivo, mime_type, tamanho_bytes, sha256_hash, observacao,
                   data_emissao, data_validade, COALESCE(situacao, 'ativo') AS situacao,
                   COALESCE(versao, 1) AS versao, documento_raiz_id,
                   enviado_por, criado_em, inativado_por, inativado_em, motivo_inativacao
            FROM colaborador_documentos
            WHERE colaborador_id = {P}
        """
        params: List[Any] = [colaborador_id]
        if not incluir_inativos:
            sql += " AND COALESCE(situacao, 'ativo') = 'ativo'"
        if categoria and categoria != "todas":
            sql += f" AND (LOWER(COALESCE(categoria, tipo_documento)) = LOWER({P}) OR LOWER(tipo_documento) = LOWER({P}))"
            params.extend([categoria.strip(), categoria.strip()])
        if termo and termo.strip():
            t = f"%{termo.strip()}%"
            sql += f" AND (LOWER(nome_arquivo) LIKE LOWER({P}) OR LOWER(COALESCE(observacao, '')) LIKE LOWER({P}))"
            params.extend([t, t])
        sql += " ORDER BY id DESC"
        cursor.execute(sql, tuple(params))
        docs = self._fetchall(cursor)
        conn.close()
        return docs

    def listar_versoes_documento(self, colaborador_id: int, doc_id: int, empresa_id: str = None) -> list:
        """Retorna histórico de versões de um documento (RF-007)."""
        self.obter_por_id(colaborador_id, empresa_id=empresa_id)
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT id, documento_raiz_id FROM colaborador_documentos WHERE id = {P} AND colaborador_id = {P}",
            (doc_id, colaborador_id),
        )
        ref = self._fetchone(cursor)
        if not ref:
            conn.close()
            raise RecursoNaoEncontradoException("Documento não encontrado para este colaborador.")
        raiz = int(ref.get("documento_raiz_id") or ref["id"])
        cursor.execute(
            f"""SELECT id, colaborador_id, tipo_documento, categoria, nome_arquivo, mime_type,
                       tamanho_bytes, data_emissao, data_validade, situacao, versao,
                       documento_raiz_id, enviado_por, criado_em, inativado_por, inativado_em
                FROM colaborador_documentos
                WHERE colaborador_id = {P} AND (id = {P} OR documento_raiz_id = {P})
                ORDER BY versao DESC, id DESC""",
            (colaborador_id, raiz, raiz),
        )
        rows = self._fetchall(cursor)
        conn.close()
        return rows

    def obter_documento_para_download(
        self,
        colaborador_id: int,
        doc_id: int,
        usuario: str = "Sistema/Administrador",
        empresa_id: str = None,
        ip_origem: Optional[str] = None,
        acao: str = "download",
    ) -> dict:
        """Valida acesso, lê bytes do armazenamento privado e audita o acesso ao documento (RF-007)."""
        colab = self.obter_por_id(colaborador_id, empresa_id=empresa_id)
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        sql = f"SELECT * FROM colaborador_documentos WHERE id = {P} AND colaborador_id = {P}"
        params: List[Any] = [doc_id, colaborador_id]
        if empresa_id and empresa_id.strip():
            sql += f" AND (empresa_id = {P} OR empresa_id IS NULL)"
            params.append(empresa_id.strip())
        cursor.execute(sql, tuple(params))
        doc = self._fetchone(cursor)
        if not doc:
            conn.close()
            raise RecursoNaoEncontradoException("Documento não encontrado ou acesso não autorizado.")

        conteudo_bytes = b""
        caminho = doc.get("caminho_privado")
        if caminho and os.path.exists(caminho):
            with open(caminho, "rb") as f:
                conteudo_bytes = f.read()
        elif doc.get("conteudo_base64"):
            conteudo_bytes = self._decodificar_base64(doc["conteudo_base64"])

        emp_id = colab.get("empresa_id") or "a0000000-0000-0000-0000-000000000001"
        self._registrar_auditoria_cadastral(
            cursor, colaborador_id, emp_id,
            entidade="documento", operacao=acao,
            campo_alterado=f"Acesso a Documento ({acao})",
            valor_anterior=None,
            valor_novo=f"{doc['nome_arquivo']} (v{doc.get('versao', 1)})",
            usuario=usuario, origem=f"DOCUMENTO_{acao.upper()}", ip_origem=ip_origem,
        )
        conn.commit()
        conn.close()
        return {
            "id": doc["id"],
            "nome_arquivo": doc["nome_arquivo"],
            "mime_type": doc.get("mime_type") or "application/octet-stream",
            "tamanho_bytes": len(conteudo_bytes) or int(doc.get("tamanho_bytes") or 0),
            "situacao": doc.get("situacao", "ativo"),
            "versao": doc.get("versao", 1),
            "conteudo_bytes": conteudo_bytes,
        }

    def remover_documento(
        self,
        colaborador_id: int,
        doc_id: int,
        usuario: str = "Sistema/Administrador",
        motivo: str = "",
        empresa_id: str = None,
        origem: str = "API",
        ip_origem: Optional[str] = None,
    ) -> bool:
        """Inativa logicamente um documento preservando o arquivo e sua rastreabilidade (RF-007)."""
        colab = self.obter_por_id(colaborador_id, empresa_id=empresa_id)
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT id, nome_arquivo, COALESCE(situacao, 'ativo') AS situacao FROM colaborador_documentos WHERE id = {P} AND colaborador_id = {P}",
            (doc_id, colaborador_id),
        )
        row = self._fetchone(cursor)
        if not row:
            conn.close()
            raise RecursoNaoEncontradoException("Documento não encontrado para este colaborador.")

        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        emp_id = colab.get("empresa_id") or "a0000000-0000-0000-0000-000000000001"
        cursor.execute(
            f"""UPDATE colaborador_documentos
                SET situacao = 'inativo', inativado_por = {P}, inativado_em = {P}, motivo_inativacao = {P}
                WHERE id = {P} AND colaborador_id = {P}""",
            (usuario, agora, (motivo or "Inativação solicitada pelo operador").strip(), doc_id, colaborador_id),
        )
        self._registrar_auditoria_cadastral(
            cursor, colaborador_id, emp_id,
            entidade="documento", operacao="inativacao",
            campo_alterado="Documento Inativado",
            valor_anterior=row["nome_arquivo"], valor_novo="inativo",
            usuario=usuario, origem=origem, ip_origem=ip_origem,
            justificativa=(motivo or "").strip(), agora=agora,
        )
        conn.commit()
        conn.close()
        return True

    # ──────────────────────────────────────────────────────────
    # RF-008: Controle de Documentação, Validade e Alertas
    # ──────────────────────────────────────────────────────────

    def listar_categorias_documentos(self, empresa_id: Optional[str] = None, apenas_ativas: bool = True) -> list:
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        sql = "SELECT * FROM documentos_categorias WHERE 1=1"
        params: List[Any] = []
        if empresa_id:
            sql += f" AND (empresa_id = {P} OR empresa_id = 'a0000000-0000-0000-0000-000000000001')"
            params.append(empresa_id.strip())
        if apenas_ativas:
            sql += " AND ativo = 1"
        sql += " ORDER BY id ASC"
        cursor.execute(sql, tuple(params))
        rows = self._fetchall(cursor)
        conn.close()
        return rows

    def criar_categoria_documento(self, dados: dict, usuario: str = "Sistema/Administrador", empresa_id: Optional[str] = None) -> dict:
        nome = (dados.get("nome") or "").strip()
        codigo = (dados.get("codigo") or nome.upper().replace(" ", "_")).strip().upper()
        if not nome or not codigo:
            raise ValidacaoException({"nome": "Nome e código da categoria são obrigatórios."})
        emp_id = (empresa_id or dados.get("empresa_id") or "a0000000-0000-0000-0000-000000000001").strip()
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(f"SELECT id FROM documentos_categorias WHERE UPPER(codigo) = UPPER({P})", (codigo,))
        if cursor.fetchone():
            conn.close()
            raise ValidacaoException({"codigo": f"Já existe uma categoria de documento com código '{codigo}'."})
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        obrig = 1 if dados.get("obrigatorio") in (1, True, "1", "true") else 0
        ex_val = 1 if dados.get("exige_validade") in (1, True, "1", "true") else 0
        sql_pg = f"INSERT INTO documentos_categorias (empresa_id, codigo, nome, obrigatorio, exige_validade, ativo, criado_em) VALUES ({P},{P},{P},{P},{P},1,{P}) RETURNING id"
        sql_sqlite = f"INSERT INTO documentos_categorias (empresa_id, codigo, nome, obrigatorio, exige_validade, ativo, criado_em) VALUES ({P},{P},{P},{P},{P},1,{P})"
        cid = self._insert_id(cursor, conn, sql_pg, sql_sqlite, (emp_id, codigo, nome, obrig, ex_val, agora))
        conn.commit()
        cursor.execute(f"SELECT * FROM documentos_categorias WHERE id = {P}", (cid,))
        row = self._fetchone(cursor)
        conn.close()
        return row

    def obter_config_alertas_documentos(self, empresa_id: Optional[str] = None) -> dict:
        emp_id = (empresa_id or "a0000000-0000-0000-0000-000000000001").strip()
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM documentos_config_alertas WHERE empresa_id = {P} ORDER BY id DESC LIMIT 1", (emp_id,))
        row = self._fetchone(cursor)
        if not row:
            cursor.execute("SELECT * FROM documentos_config_alertas ORDER BY id DESC LIMIT 1")
            row = self._fetchone(cursor)
        conn.close()
        if not row:
            return {
                "empresa_id": emp_id,
                "dias_alertas": [30, 15, 7],
                "dias_antecedencia_alerta": [30, 15, 7],
                "tamanho_max_mb": 10,
                "tamanho_maximo_mb": 10,
            }
        try:
            dias = sorted({int(d) for d in json.loads(row["dias_alertas_json"]) if int(d) > 0}, reverse=True)
        except Exception:
            dias = [30, 15, 7]
        dias_fin = dias or [30, 15, 7]
        max_mb_fin = int(row.get("tamanho_max_mb") or 10)
        return {
            "id": row["id"],
            "empresa_id": row["empresa_id"],
            "dias_alertas": dias_fin,
            "dias_antecedencia_alerta": dias_fin,
            "tamanho_max_mb": max_mb_fin,
            "tamanho_maximo_mb": max_mb_fin,
            "atualizado_por": row.get("atualizado_por"),
            "atualizado_em": row.get("atualizado_em"),
        }

    def atualizar_config_alertas_documentos(self, dados: dict, usuario: str = "Sistema/Administrador", empresa_id: Optional[str] = None) -> dict:
        emp_id = (empresa_id or (dados or {}).get("empresa_id") or "a0000000-0000-0000-0000-000000000001").strip()
        dias_raw = (dados or {}).get("dias_alertas")
        if dias_raw is None:
            dias_raw = (dados or {}).get("dias_antecedencia_alerta")
        if isinstance(dias_raw, str):
            dias_raw = [x.strip() for x in dias_raw.split(",") if x.strip()]
        if not isinstance(dias_raw, list) or not dias_raw:
            raise ValidacaoException({"dias_alertas": "Informe uma lista válida de dias para alerta (ex: [30, 15, 7])."})
        try:
            dias_clean = sorted({int(x) for x in dias_raw}, reverse=True)
        except (TypeError, ValueError):
            raise ValidacaoException({"dias_alertas": "Os prazos de alerta devem ser números inteiros positivos."})
        if any(d <= 0 or d > 365 for d in dias_clean):
            raise ValidacaoException({"dias_alertas": "Os prazos de alerta devem estar entre 1 e 365 dias."})

        max_mb_raw = (dados or {}).get("tamanho_max_mb")
        if max_mb_raw is None:
            max_mb_raw = (dados or {}).get("tamanho_maximo_mb", 10)
        max_mb = int(max_mb_raw or 10)
        if max_mb < 1 or max_mb > 100:
            raise ValidacaoException({"tamanho_max_mb": "Tamanho máximo de arquivo deve estar entre 1 MB e 100 MB."})

        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(f"SELECT id FROM documentos_config_alertas WHERE empresa_id = {P}", (emp_id,))
        ex = cursor.fetchone()
        dias_json = json.dumps(dias_clean)
        if ex:
            cursor.execute(
                f"UPDATE documentos_config_alertas SET dias_alertas_json={P}, tamanho_max_mb={P}, atualizado_por={P}, atualizado_em={P} WHERE id={P}",
                (dias_json, max_mb, usuario, agora, ex[0]),
            )
        else:
            cursor.execute(
                f"INSERT INTO documentos_config_alertas (empresa_id, dias_alertas_json, tamanho_max_mb, atualizado_por, atualizado_em) VALUES ({P},{P},{P},{P},{P})",
                (emp_id, dias_json, max_mb, usuario, agora),
            )
        conn.commit()
        conn.close()
        return self.obter_config_alertas_documentos(empresa_id=emp_id)

    def obter_controle_documentacao(
        self,
        empresa_id: Optional[str] = None,
        situacao: Optional[str] = None,
        categoria: Optional[str] = None,
        colaborador_id: Optional[int] = None,
        data_referencia: Optional[str] = None,
        sincronizar_pendencias: bool = False,
    ) -> dict:
        """RF-008: Painel central de validade, vencidos, próximos do vencimento, pendentes e sem validade."""
        cfg = self.obter_config_alertas_documentos(empresa_id=empresa_id)
        dias_alertas = sorted(cfg["dias_alertas"], reverse=True)
        janela_alerta = max(dias_alertas) if dias_alertas else 30
        ref_dt = converter_para_data(data_referencia) if data_referencia else date.today()
        if not ref_dt:
            ref_dt = date.today()

        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()

        sql_docs = """
            SELECT d.id, d.colaborador_id, d.empresa_id, d.tipo_documento,
                   COALESCE(d.categoria, d.tipo_documento) AS categoria,
                   d.nome_arquivo, d.data_emissao, d.data_validade,
                   COALESCE(d.situacao, 'ativo') AS situacao_registro,
                   COALESCE(d.versao, 1) AS versao, d.criado_em,
                   c.nome_completo AS colaborador_nome, c.matricula AS colaborador_matricula,
                   c.setor AS colaborador_setor
            FROM colaborador_documentos d
            JOIN colaboradores c ON c.id = d.colaborador_id
            WHERE COALESCE(d.situacao, 'ativo') != 'substituido'
        """
        params: List[Any] = []
        if empresa_id:
            sql_docs += f" AND (d.empresa_id = {P} OR d.empresa_id IS NULL)"
            params.append(empresa_id.strip())
        if colaborador_id:
            sql_docs += f" AND d.colaborador_id = {P}"
            params.append(int(colaborador_id))
        sql_docs += " ORDER BY d.id DESC"
        cursor.execute(sql_docs, tuple(params))
        docs = self._fetchall(cursor)

        categorias = self.listar_categorias_documentos(empresa_id=empresa_id, apenas_ativas=True)
        cats_obrig = [c for c in categorias if int(c.get("obrigatorio") or 0) == 1]

        sql_colabs = "SELECT id, nome_completo, matricula, setor, empresa_id FROM colaboradores WHERE situacao = 'ativo'"
        p_col: List[Any] = []
        if empresa_id:
            sql_colabs += f" AND (empresa_id = {P} OR empresa_id IS NULL)"
            p_col.append(empresa_id.strip())
        if colaborador_id:
            sql_colabs += f" AND id = {P}"
            p_col.append(int(colaborador_id))
        cursor.execute(sql_colabs, tuple(p_col))
        colabs_ativos = self._fetchall(cursor)

        docs_por_colab_cat = set()
        itens = []
        contadores = {
            "total_documentos": 0,
            "regulares": 0,
            "proximos_vencimento": 0,
            "vencidos": 0,
            "pendentes": 0,
            "sem_validade": 0,
            "inativos": 0,
        }

        for d in docs:
            contadores["total_documentos"] += 1
            cat_doc = str(d.get("categoria") or d.get("tipo_documento") or "").strip()
            sit_reg = str(d.get("situacao_registro") or "ativo").lower()
            if sit_reg == "ativo":
                docs_por_colab_cat.add((int(d["colaborador_id"]), cat_doc.lower()))
                docs_por_colab_cat.add((int(d["colaborador_id"]), str(d.get("tipo_documento") or "").strip().lower()))

            dias_rest = None
            faixa_alerta = None
            if sit_reg == "inativo":
                status_val = "inativo"
                contadores["inativos"] += 1
            else:
                val_str = (d.get("data_validade") or "").strip()
                if not val_str:
                    status_val = "sem_validade"
                    contadores["sem_validade"] += 1
                else:
                    val_dt = converter_para_data(val_str)
                    if not val_dt:
                        status_val = "sem_validade"
                        contadores["sem_validade"] += 1
                    else:
                        dias_rest = (val_dt - ref_dt).days
                        if dias_rest < 0:
                            status_val = "vencido"
                            contadores["vencidos"] += 1
                        elif dias_rest <= janela_alerta:
                            status_val = "proximo_vencimento"
                            contadores["proximos_vencimento"] += 1
                            faixa_alerta = min((da for da in dias_alertas if da >= dias_rest), default=janela_alerta)
                        else:
                            status_val = "regular"
                            contadores["regulares"] += 1

            itens.append({
                "documento_id": d["id"],
                "colaborador_id": d["colaborador_id"],
                "colaborador_nome": d["colaborador_nome"],
                "matricula": d["colaborador_matricula"],
                "setor": d["colaborador_setor"],
                "categoria": cat_doc,
                "nome_arquivo": d["nome_arquivo"],
                "data_emissao": d.get("data_emissao"),
                "data_validade": d.get("data_validade"),
                "versao": d.get("versao", 1),
                "situacao_validade": status_val,
                "dias_restantes": dias_rest,
                "faixa_alerta_dias": faixa_alerta,
            })

        # Documentos obrigatórios pendentes por colaborador ativo
        for col in colabs_ativos:
            cid = int(col["id"])
            for cat in cats_obrig:
                c_nome = str(cat["nome"]).strip()
                c_cod = str(cat["codigo"]).strip()
                if (cid, c_nome.lower()) not in docs_por_colab_cat and (cid, c_cod.lower()) not in docs_por_colab_cat:
                    contadores["pendentes"] += 1
                    itens.append({
                        "documento_id": None,
                        "colaborador_id": cid,
                        "colaborador_nome": col["nome_completo"],
                        "matricula": col["matricula"],
                        "setor": col["setor"],
                        "categoria": c_nome,
                        "nome_arquivo": "(Documento obrigatório pendente)",
                        "data_emissao": None,
                        "data_validade": None,
                        "versao": 0,
                        "situacao_validade": "pendente",
                        "dias_restantes": None,
                        "faixa_alerta_dias": None,
                    })

        if sincronizar_pendencias:
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            emp_pend = empresa_id or "a0000000-0000-0000-0000-000000000001"
            for it in itens:
                if it["situacao_validade"] in ("vencido", "proximo_vencimento") and it["documento_id"]:
                    titulo_p = f"Documento {it['situacao_validade'].upper()}: {it['categoria']} — {it['colaborador_nome']} (#{it['documento_id']})"
                    cursor.execute(
                        f"SELECT id FROM pendencias_operacionais WHERE titulo = {P} AND status != 'resolvida'",
                        (titulo_p,),
                    )
                    if not cursor.fetchone():
                        sev = "alta" if it["situacao_validade"] == "vencido" else "media"
                        cursor.execute(
                            f"""INSERT INTO pendencias_operacionais (
                                    empresa_id, modulo, tipo_pendencia, titulo, descricao, severidade,
                                    colaborador_id, prazo_limite, responsavel, status, criado_em
                                ) VALUES ({P},'Documentação','validade_documento',{P},{P},{P},{P},{P},'DP / RH','pendente',{P})""",
                            (
                                emp_pend, titulo_p,
                                f"Arquivo '{it['nome_arquivo']}' ({it['categoria']}) com validade {it['data_validade']} ({it['situacao_validade']}).",
                                sev, it["colaborador_id"], it["data_validade"] or ref_dt.strftime("%Y-%m-%d"), agora,
                            ),
                        )
            conn.commit()

        conn.close()

        filtrados = itens
        if situacao and situacao != "todas":
            filtrados = [i for i in filtrados if i["situacao_validade"] == situacao.strip().lower()]
        if categoria and categoria != "todas":
            filtrados = [i for i in filtrados if i["categoria"].lower() == categoria.strip().lower()]

        return {
            "data_referencia": ref_dt.strftime("%Y-%m-%d"),
            "config_alertas": cfg,
            "resumo": contadores,
            "itens": filtrados,
        }

    # ──────────────────────────────────────────────────────────
    # RF-009: Dados Bancários Individuais
    # ──────────────────────────────────────────────────────────

    def listar_dados_bancarios(self, colaborador_id: int, incluir_inativos: bool = False, empresa_id: str = None) -> list:
        self.obter_por_id(colaborador_id, empresa_id=empresa_id)
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        sql = f"SELECT * FROM colaborador_dados_bancarios WHERE colaborador_id = {P}"
        if not incluir_inativos:
            sql += " AND ativo = 1"
        sql += " ORDER BY principal DESC, id DESC"
        cursor.execute(sql, (colaborador_id,))
        rows = self._fetchall(cursor)
        conn.close()
        return rows

    def cadastrar_dados_bancarios(
        self,
        colaborador_id: int,
        dados: dict,
        usuario: str = "Sistema/Administrador",
        origem: str = "API",
        ip_origem: Optional[str] = None,
        empresa_id: str = None,
    ) -> dict:
        colab = self.obter_por_id(colaborador_id, empresa_id=empresa_id)
        dados_proc = dict(dados or {})
        if "titular_nome" not in dados_proc:
            dados_proc["titular_nome"] = colab["nome_completo"]
        if "titular_cpf" not in dados_proc and "cpf_titular" not in dados_proc:
            dados_proc["titular_cpf"] = colab["cpf"]
        ok, erros, sanit = validar_dados_bancarios(dados_proc)
        if not ok:
            raise ValidacaoException(erros)

        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        emp_id = colab.get("empresa_id") or "a0000000-0000-0000-0000-000000000001"

        if sanit["principal"] == 1:
            cursor.execute(f"UPDATE colaborador_dados_bancarios SET principal = 0 WHERE colaborador_id = {P}", (colaborador_id,))

        sql_pg = f"""
            INSERT INTO colaborador_dados_bancarios (
                colaborador_id, empresa_id, banco_codigo, banco_nome, agencia, agencia_digito,
                conta, conta_digito, tipo_conta, chave_pix_tipo, chave_pix, titular_nome,
                titular_cpf, principal, ativo, criado_por, criado_em, atualizado_por, atualizado_em
            ) VALUES ({P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},1,{P},{P},{P},{P}) RETURNING id
        """
        sql_sqlite = f"""
            INSERT INTO colaborador_dados_bancarios (
                colaborador_id, empresa_id, banco_codigo, banco_nome, agencia, agencia_digito,
                conta, conta_digito, tipo_conta, chave_pix_tipo, chave_pix, titular_nome,
                titular_cpf, principal, ativo, criado_por, criado_em, atualizado_por, atualizado_em
            ) VALUES ({P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},{P},1,{P},{P},{P},{P})
        """
        cid = self._insert_id(cursor, conn, sql_pg, sql_sqlite, (
            colaborador_id, emp_id, sanit["banco_codigo"], sanit["banco_nome"],
            sanit["agencia"], sanit["agencia_digito"], sanit["conta"], sanit["conta_digito"],
            sanit["tipo_conta"], sanit["chave_pix_tipo"], sanit["chave_pix"],
            sanit["titular_nome"], sanit["titular_cpf"], sanit["principal"],
            usuario, agora, usuario, agora,
        ))
        self._registrar_auditoria_cadastral(
            cursor, colaborador_id, emp_id,
            entidade="dados_bancarios", operacao="inclusao",
            campo_alterado="Conta Bancária Cadastrada",
            valor_anterior=None,
            valor_novo=f"Banco {sanit['banco_codigo']} ({sanit['banco_nome']}) Ag {sanit['agencia']} CC {sanit['conta']}-{sanit['conta_digito']}",
            usuario=usuario, origem=origem, ip_origem=ip_origem, agora=agora,
        )
        conn.commit()
        cursor.execute(f"SELECT * FROM colaborador_dados_bancarios WHERE id = {P}", (cid,))
        row = self._fetchone(cursor)
        conn.close()
        return row

    def atualizar_dados_bancarios(
        self,
        colaborador_id: int,
        conta_id: int,
        dados: dict,
        usuario: str = "Sistema/Administrador",
        origem: str = "API",
        ip_origem: Optional[str] = None,
        empresa_id: str = None,
    ) -> dict:
        colab = self.obter_por_id(colaborador_id, empresa_id=empresa_id)
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM colaborador_dados_bancarios WHERE id = {P} AND colaborador_id = {P}", (conta_id, colaborador_id))
        atual = self._fetchone(cursor)
        if not atual:
            conn.close()
            raise RecursoNaoEncontradoException("Dados bancários não encontrados para este colaborador.")

        merged = {**atual, **(dados or {})}
        ok, erros, sanit = validar_dados_bancarios(merged)
        if not ok:
            conn.close()
            raise ValidacaoException(erros)

        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        emp_id = colab.get("empresa_id") or "a0000000-0000-0000-0000-000000000001"
        if sanit["principal"] == 1:
            cursor.execute(
                f"UPDATE colaborador_dados_bancarios SET principal = 0 WHERE colaborador_id = {P} AND id != {P}",
                (colaborador_id, conta_id),
            )

        cursor.execute(f"""
            UPDATE colaborador_dados_bancarios SET
                banco_codigo={P}, banco_nome={P}, agencia={P}, agencia_digito={P},
                conta={P}, conta_digito={P}, tipo_conta={P}, chave_pix_tipo={P},
                chave_pix={P}, titular_nome={P}, titular_cpf={P}, principal={P},
                ativo={P}, atualizado_por={P}, atualizado_em={P}
            WHERE id={P} AND colaborador_id={P}
        """, (
            sanit["banco_codigo"], sanit["banco_nome"], sanit["agencia"], sanit["agencia_digito"],
            sanit["conta"], sanit["conta_digito"], sanit["tipo_conta"], sanit["chave_pix_tipo"],
            sanit["chave_pix"], sanit["titular_nome"], sanit["titular_cpf"], sanit["principal"],
            sanit["ativo"], usuario, agora, conta_id, colaborador_id,
        ))
        self._registrar_auditoria_cadastral(
            cursor, colaborador_id, emp_id,
            entidade="dados_bancarios", operacao="alteracao",
            campo_alterado=f"Conta Bancária #{conta_id}",
            valor_anterior=f"Banco {atual['banco_codigo']} Ag {atual['agencia']} CC {atual['conta']}",
            valor_novo=f"Banco {sanit['banco_codigo']} Ag {sanit['agencia']} CC {sanit['conta']} (Principal={sanit['principal']})",
            usuario=usuario, origem=origem, ip_origem=ip_origem, agora=agora,
        )
        conn.commit()
        cursor.execute(f"SELECT * FROM colaborador_dados_bancarios WHERE id = {P}", (conta_id,))
        row = self._fetchone(cursor)
        conn.close()
        return row

    def inativar_dados_bancarios(
        self,
        colaborador_id: int,
        conta_id: int,
        usuario: str = "Sistema/Administrador",
        origem: str = "API",
        ip_origem: Optional[str] = None,
        empresa_id: str = None,
    ) -> dict:
        colab = self.obter_por_id(colaborador_id, empresa_id=empresa_id)
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM colaborador_dados_bancarios WHERE id = {P} AND colaborador_id = {P}", (conta_id, colaborador_id))
        atual = self._fetchone(cursor)
        if not atual:
            conn.close()
            raise RecursoNaoEncontradoException("Conta bancária não encontrada.")

        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        emp_id = colab.get("empresa_id") or "a0000000-0000-0000-0000-000000000001"
        cursor.execute(
            f"UPDATE colaborador_dados_bancarios SET ativo = 0, principal = 0, atualizado_por = {P}, atualizado_em = {P} WHERE id = {P}",
            (usuario, agora, conta_id),
        )
        self._registrar_auditoria_cadastral(
            cursor, colaborador_id, emp_id,
            entidade="dados_bancarios", operacao="inativacao",
            campo_alterado=f"Conta Bancária #{conta_id}",
            valor_anterior=f"Banco {atual['banco_codigo']} CC {atual['conta']}",
            valor_novo="inativa",
            usuario=usuario, origem=origem, ip_origem=ip_origem, agora=agora,
        )
        conn.commit()
        cursor.execute(f"SELECT * FROM colaborador_dados_bancarios WHERE id = {P}", (conta_id,))
        row = self._fetchone(cursor)
        conn.close()
        return row

    # ──────────────────────────────────────────────────────────
    # RF-010: Consulta Filtrada de Auditoria Cadastral
    # ──────────────────────────────────────────────────────────

    def listar_auditoria_cadastral(
        self,
        colaborador_id: Optional[int] = None,
        entidade: Optional[str] = None,
        usuario: Optional[str] = None,
        campo: Optional[str] = None,
        data_inicio: Optional[str] = None,
        data_fim: Optional[str] = None,
        empresa_id: Optional[str] = None,
    ) -> list:
        if colaborador_id is not None:
            self.obter_por_id(colaborador_id, empresa_id=empresa_id)
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        sql = """
            SELECT h.id, h.colaborador_id, c.nome_completo AS colaborador_nome, c.matricula,
                   h.data_hora, COALESCE(h.entidade, 'colaborador') AS entidade,
                   COALESCE(h.operacao, 'alteracao') AS operacao,
                   h.campo_alterado, h.valor_anterior, h.valor_novo,
                   h.usuario_responsavel, h.origem, h.ip_origem, h.justificativa
            FROM historico_alteracoes h
            JOIN colaboradores c ON c.id = h.colaborador_id
            WHERE 1=1
        """
        params: List[Any] = []
        if colaborador_id is not None:
            sql += f" AND h.colaborador_id = {P}"
            params.append(int(colaborador_id))
        if empresa_id and self._tabela_tem_coluna(cursor, "colaboradores", "empresa_id"):
            sql += f" AND (c.empresa_id = {P} OR c.empresa_id IS NULL)"
            params.append(empresa_id.strip())
        if entidade and entidade != "todas":
            sql += f" AND COALESCE(h.entidade, 'colaborador') = {P}"
            params.append(entidade.strip().lower())
        if usuario and usuario.strip():
            sql += f" AND LOWER(h.usuario_responsavel) LIKE LOWER({P})"
            params.append(f"%{usuario.strip()}%")
        if campo and campo.strip():
            sql += f" AND LOWER(h.campo_alterado) LIKE LOWER({P})"
            params.append(f"%{campo.strip()}%")
        if data_inicio:
            sql += f" AND SUBSTR(h.data_hora, 1, 10) >= {P}"
            params.append(data_inicio.strip()[:10])
        if data_fim:
            sql += f" AND SUBSTR(h.data_hora, 1, 10) <= {P}"
            params.append(data_fim.strip()[:10])
        sql += " ORDER BY h.id DESC LIMIT 300"
        cursor.execute(sql, tuple(params))
        rows = self._fetchall(cursor)
        conn.close()
        return rows
