"""
Camada de Servicos de Negocio — Colaboradores
Contem a logica de aplicacao, auditoria de alteracoes, validacoes de duplicidade
e manipulacao de dados conforme RF-01 a RF-09 e CA-01 a CA-08.
Funciona com PostgreSQL (producao) e SQLite (desenvolvimento local e testes).
"""
import json
from datetime import datetime

from .database import _usar_postgres, fetchall_dict, fetchone_dict, get_connection, init_db, insert_returning_id, ph
from .validators import normalizar_cpf, validar_formulario_colaborador

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
    # Shortcut helpers que carregam db_path automaticamente
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

    def _tabela_tem_coluna(self, cursor, tabela: str, coluna: str) -> bool:
        """Verifica de forma resiliente e compatível se a tabela possui a coluna informada."""
        try:
            if self._pg():
                cursor.execute(
                    "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
                    (tabela, coluna)
                )
                return cursor.fetchone() is not None
            else:
                cursor.execute(f"PRAGMA table_info({tabela})")
                cols = [row[1] if isinstance(row, (tuple, list)) else row["name"] for row in cursor.fetchall()]
                return coluna in cols
        except Exception:
            return False

    # ──────────────────────────────────────────────────────────
    # CRUD
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

    def cadastrar(self, dados: dict, usuario: str = "Sistema/Administrador") -> dict:
        """Cadastra um novo colaborador com validacao e checagem de duplicidade."""
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
                    colaborador_id, nome, cpf, parentesco,
                    data_nascimento, eh_dependente_irrf, eh_elegivel_salario_familia
                ) VALUES ({P},{P},{P},{P},{P},{P},{P})
            """, (
                colaborador_id, dep["nome"], dep.get("cpf", ""), dep["parentesco"],
                dep.get("data_nascimento", ""), int(dep.get("eh_dependente_irrf", 1)),
                int(dep.get("eh_elegivel_salario_familia", 0))
            ))

        cursor.execute(f"""
            INSERT INTO historico_alteracoes (
                colaborador_id, data_hora, campo_alterado,
                valor_anterior, valor_novo, usuario_responsavel
            ) VALUES ({P},{P},{P},{P},{P},{P})
        """, (
            colaborador_id, agora, "Criacao de Cadastro",
            None,
            f"Colaborador {sanitizado['nome_completo']} admitido com matricula {sanitizado['matricula']}.",
            usuario,
        ))

        conn.commit()
        conn.close()
        return self.obter_por_id(colaborador_id)

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
    ) -> dict:
        """Anexa um documento cadastral ao colaborador com trilha de auditoria."""
        colab = self.obter_por_id(colaborador_id)
        if not (tipo_documento or "").strip() or not (nome_arquivo or "").strip():
            raise ValidacaoException({"documento": "Tipo de documento e nome do arquivo são obrigatórios."})

        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        empresa_id = colab.get("empresa_id") or "a0000000-0000-0000-0000-000000000001"

        sql_pg = """
            INSERT INTO colaborador_documentos (
                colaborador_id, empresa_id, tipo_documento, nome_arquivo,
                mime_type, tamanho_bytes, conteudo_base64, observacao, enviado_por, criado_em
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """
        sql_sqlite = """
            INSERT INTO colaborador_documentos (
                colaborador_id, empresa_id, tipo_documento, nome_arquivo,
                mime_type, tamanho_bytes, conteudo_base64, observacao, enviado_por, criado_em
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
        """
        doc_id = self._insert_id(cursor, conn, sql_pg, sql_sqlite, (
            colaborador_id, empresa_id, tipo_documento.strip(), nome_arquivo.strip(),
            (mime_type or "application/octet-stream").strip(), int(tamanho_bytes or 0),
            conteudo_base64 or "", (observacao or "").strip(), usuario, agora
        ))
        cursor.execute(f"""
            INSERT INTO historico_alteracoes (
                colaborador_id, data_hora, campo_alterado, valor_anterior, valor_novo, usuario_responsavel
            ) VALUES ({P},{P},{P},{P},{P},{P})
        """, (colaborador_id, agora, "Documento Anexado", None, f"{tipo_documento.strip()}: {nome_arquivo.strip()}", usuario))

        conn.commit()
        cursor.execute(f"SELECT id, colaborador_id, tipo_documento, nome_arquivo, mime_type, tamanho_bytes, observacao, enviado_por, criado_em FROM colaborador_documentos WHERE id = {P}", (doc_id,))
        doc = self._fetchone(cursor)
        conn.close()
        return doc

    def listar_documentos(self, colaborador_id: int) -> list:
        """Lista os documentos anexados do colaborador."""
        self.obter_por_id(colaborador_id)
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT id, colaborador_id, tipo_documento, nome_arquivo, mime_type, tamanho_bytes, observacao, enviado_por, criado_em FROM colaborador_documentos WHERE colaborador_id = {P} ORDER BY id DESC",
            (colaborador_id,)
        )
        docs = self._fetchall(cursor)
        conn.close()
        return docs

    def remover_documento(self, colaborador_id: int, doc_id: int, usuario: str = "Sistema/Administrador") -> bool:
        """Remove um documento anexado do colaborador."""
        self.obter_por_id(colaborador_id)
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(f"SELECT nome_arquivo FROM colaborador_documentos WHERE id = {P} AND colaborador_id = {P}", (doc_id, colaborador_id))
        row = cursor.fetchone()
        if not row:
            conn.close()
            raise RecursoNaoEncontradoException("Documento não encontrado para este colaborador.")
        nome_arq = row[0]
        cursor.execute(f"DELETE FROM colaborador_documentos WHERE id = {P} AND colaborador_id = {P}", (doc_id, colaborador_id))
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(f"""
            INSERT INTO historico_alteracoes (
                colaborador_id, data_hora, campo_alterado, valor_anterior, valor_novo, usuario_responsavel
            ) VALUES ({P},{P},{P},{P},{P},{P})
        """, (colaborador_id, agora, "Documento Removido", nome_arq, None, usuario))
        conn.commit()
        conn.close()
        return True

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
        """Lista colaboradores com pesquisa e filtros por nome, matrícula, CPF, cargo, setor e empresa (RF-002, Multiempresa)."""
        P = self._ph()
        pg = self._pg()

        conn = self._conn()
        cursor = conn.cursor()

        sql = """
            SELECT c.*, COUNT(d.id) AS total_dependentes
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
            if pg:
                sql += f" AND c.setor ILIKE {P}"
            else:
                sql += f" AND LOWER(c.setor) LIKE LOWER({P})"
            params.append(padrao_setor)

        if cargo and cargo.strip():
            padrao_cargo = f"%{cargo.strip()}%"
            if pg:
                sql += f" AND c.cargo ILIKE {P}"
            else:
                sql += f" AND LOWER(c.cargo) LIKE LOWER({P})"
            params.append(padrao_cargo)

        if nome and nome.strip():
            padrao_nome = f"%{nome.strip()}%"
            if pg:
                sql += f" AND c.nome_completo ILIKE {P}"
            else:
                sql += f" AND LOWER(c.nome_completo) LIKE LOWER({P})"
            params.append(padrao_nome)

        if matricula and matricula.strip():
            padrao_mat = f"%{matricula.strip()}%"
            if pg:
                sql += f" AND c.matricula ILIKE {P}"
            else:
                sql += f" AND LOWER(c.matricula) LIKE LOWER({P})"
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
        """Retorna dados completos do colaborador, dependentes e historico com validação multi-tenant."""
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
                       COALESCE(data_nascimento, '') AS data_nascimento,
                       COALESCE(eh_dependente_irrf, 1) AS eh_dependente_irrf,
                       COALESCE(eh_elegivel_salario_familia, 0) AS eh_elegivel_salario_familia
                FROM dependentes WHERE colaborador_id = {P}""",
            (colaborador_id,)
        )
        colab["dependentes"] = self._fetchall(cursor)

        try:
            cursor.execute(
                f"""SELECT id, tipo_documento, nome_arquivo, mime_type, tamanho_bytes, observacao, enviado_por, criado_em
                    FROM colaborador_documentos WHERE colaborador_id = {P} ORDER BY id DESC""",
                (colaborador_id,)
            )
            colab["documentos"] = self._fetchall(cursor)
        except Exception:
            colab["documentos"] = []

        cursor.execute(f"""
            SELECT id, data_hora, campo_alterado, valor_anterior, valor_novo, usuario_responsavel
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
        """Retorna a trilha auditada de alteracoes cadastrais do colaborador (RF-003)."""
        colab = self.obter_por_id(colaborador_id)
        return colab.get("historico", [])

    def atualizar(
        self,
        colaborador_id: int,
        dados: dict,
        usuario: str = "Sistema/Administrador",
        justificativa: str = None,
    ) -> dict:
        """Controla e audita alteracoes cadastrais do colaborador preservando o ID (RF-003)."""
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

        alteracoes = []
        for campo_bd, rotulo in CAMPOS_COMPARAVEIS:
            val_antigo = atual.get(campo_bd)
            val_novo   = sanitizado.get(campo_bd)
            str_antigo = "" if val_antigo is None else str(val_antigo).strip()
            str_novo   = "" if val_novo   is None else str(val_novo).strip()

            if campo_bd == "salario_base" and val_antigo is not None and val_novo is not None:
                if abs(float(val_antigo) - float(val_novo)) > 0.001:
                    alteracoes.append((rotulo, f"R$ {float(val_antigo):.2f}", f"R$ {float(val_novo):.2f}"))
            elif str_antigo != str_novo:
                alteracoes.append((rotulo, str_antigo, str_novo))

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

        deps_antigos = atual.get("dependentes", [])
        deps_novos   = sanitizado.get("dependentes", [])

        cursor.execute(f"DELETE FROM dependentes WHERE colaborador_id = {P}", (colaborador_id,))
        for dep in deps_novos:
            cursor.execute(f"""
                INSERT INTO dependentes (
                    colaborador_id, nome, cpf, parentesco,
                    data_nascimento, eh_dependente_irrf, eh_elegivel_salario_familia
                ) VALUES ({P},{P},{P},{P},{P},{P},{P})
            """, (
                colaborador_id, dep["nome"], dep.get("cpf", ""), dep["parentesco"],
                dep.get("data_nascimento", ""), int(dep.get("eh_dependente_irrf", 1)),
                int(dep.get("eh_elegivel_salario_familia", 0))
            ))

        if (len(deps_antigos) != len(deps_novos) or
                json.dumps(deps_antigos, sort_keys=True) != json.dumps(deps_novos, sort_keys=True)):
            alteracoes.append((
                "Dependentes",
                f"{len(deps_antigos)} dependente(s)",
                f"{len(deps_novos)} dependente(s)",
            ))

        for campo, antigo, novo in alteracoes:
            cursor.execute(f"""
                INSERT INTO historico_alteracoes (
                    colaborador_id, data_hora, campo_alterado,
                    valor_anterior, valor_novo, usuario_responsavel
                ) VALUES ({P},{P},{P},{P},{P},{P})
            """, (colaborador_id, agora, campo, antigo, novo, responsavel_auditado))

        conn.commit()
        conn.close()
        return self.obter_por_id(colaborador_id)

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
    ) -> dict:
        """Anexa um documento cadastral ao colaborador com trilha de auditoria."""
        colab = self.obter_por_id(colaborador_id)
        if not (tipo_documento or "").strip() or not (nome_arquivo or "").strip():
            raise ValidacaoException({"documento": "Tipo de documento e nome do arquivo são obrigatórios."})

        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        empresa_id = colab.get("empresa_id") or "a0000000-0000-0000-0000-000000000001"

        sql_pg = """
            INSERT INTO colaborador_documentos (
                colaborador_id, empresa_id, tipo_documento, nome_arquivo,
                mime_type, tamanho_bytes, conteudo_base64, observacao, enviado_por, criado_em
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """
        sql_sqlite = """
            INSERT INTO colaborador_documentos (
                colaborador_id, empresa_id, tipo_documento, nome_arquivo,
                mime_type, tamanho_bytes, conteudo_base64, observacao, enviado_por, criado_em
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
        """
        doc_id = self._insert_id(cursor, conn, sql_pg, sql_sqlite, (
            colaborador_id, empresa_id, tipo_documento.strip(), nome_arquivo.strip(),
            (mime_type or "application/octet-stream").strip(), int(tamanho_bytes or 0),
            conteudo_base64 or "", (observacao or "").strip(), usuario, agora
        ))
        cursor.execute(f"""
            INSERT INTO historico_alteracoes (
                colaborador_id, data_hora, campo_alterado, valor_anterior, valor_novo, usuario_responsavel
            ) VALUES ({P},{P},{P},{P},{P},{P})
        """, (colaborador_id, agora, "Documento Anexado", None, f"{tipo_documento.strip()}: {nome_arquivo.strip()}", usuario))

        conn.commit()
        cursor.execute(f"SELECT id, colaborador_id, tipo_documento, nome_arquivo, mime_type, tamanho_bytes, observacao, enviado_por, criado_em FROM colaborador_documentos WHERE id = {P}", (doc_id,))
        doc = self._fetchone(cursor)
        conn.close()
        return doc

    def listar_documentos(self, colaborador_id: int) -> list:
        """Lista os documentos anexados do colaborador."""
        self.obter_por_id(colaborador_id)
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT id, colaborador_id, tipo_documento, nome_arquivo, mime_type, tamanho_bytes, observacao, enviado_por, criado_em FROM colaborador_documentos WHERE colaborador_id = {P} ORDER BY id DESC",
            (colaborador_id,)
        )
        docs = self._fetchall(cursor)
        conn.close()
        return docs

    def remover_documento(self, colaborador_id: int, doc_id: int, usuario: str = "Sistema/Administrador") -> bool:
        """Remove um documento anexado do colaborador."""
        self.obter_por_id(colaborador_id)
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(f"SELECT nome_arquivo FROM colaborador_documentos WHERE id = {P} AND colaborador_id = {P}", (doc_id, colaborador_id))
        row = cursor.fetchone()
        if not row:
            conn.close()
            raise RecursoNaoEncontradoException("Documento não encontrado para este colaborador.")
        nome_arq = row[0]
        cursor.execute(f"DELETE FROM colaborador_documentos WHERE id = {P} AND colaborador_id = {P}", (doc_id, colaborador_id))
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(f"""
            INSERT INTO historico_alteracoes (
                colaborador_id, data_hora, campo_alterado, valor_anterior, valor_novo, usuario_responsavel
            ) VALUES ({P},{P},{P},{P},{P},{P})
        """, (colaborador_id, agora, "Documento Removido", nome_arq, None, usuario))
        conn.commit()
        conn.close()
        return True

    def inativar(self, colaborador_id: int, motivo: str = None, usuario: str = "Sistema/Administrador") -> dict:
        """Inativacao logica sem excluir historico ou dados."""
        atual = self.obter_por_id(colaborador_id)
        if atual["situacao"] == "inativo":
            return atual

        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute(f"""
            UPDATE colaboradores SET situacao='inativo', atualizado_em={P} WHERE id={P}
        """, (agora, colaborador_id))

        desc_motivo = f" (Motivo: {motivo})" if motivo and motivo.strip() else ""
        cursor.execute(f"""
            INSERT INTO historico_alteracoes (
                colaborador_id, data_hora, campo_alterado,
                valor_anterior, valor_novo, usuario_responsavel
            ) VALUES ({P},{P},{P},{P},{P},{P})
        """, (colaborador_id, agora, "Situação do Vínculo", "ativo", f"inativo{desc_motivo}", usuario))

        conn.commit()
        conn.close()
        return self.obter_por_id(colaborador_id)

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
    ) -> dict:
        """Anexa um documento cadastral ao colaborador com trilha de auditoria."""
        colab = self.obter_por_id(colaborador_id)
        if not (tipo_documento or "").strip() or not (nome_arquivo or "").strip():
            raise ValidacaoException({"documento": "Tipo de documento e nome do arquivo são obrigatórios."})

        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        empresa_id = colab.get("empresa_id") or "a0000000-0000-0000-0000-000000000001"

        sql_pg = """
            INSERT INTO colaborador_documentos (
                colaborador_id, empresa_id, tipo_documento, nome_arquivo,
                mime_type, tamanho_bytes, conteudo_base64, observacao, enviado_por, criado_em
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """
        sql_sqlite = """
            INSERT INTO colaborador_documentos (
                colaborador_id, empresa_id, tipo_documento, nome_arquivo,
                mime_type, tamanho_bytes, conteudo_base64, observacao, enviado_por, criado_em
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
        """
        doc_id = self._insert_id(cursor, conn, sql_pg, sql_sqlite, (
            colaborador_id, empresa_id, tipo_documento.strip(), nome_arquivo.strip(),
            (mime_type or "application/octet-stream").strip(), int(tamanho_bytes or 0),
            conteudo_base64 or "", (observacao or "").strip(), usuario, agora
        ))
        cursor.execute(f"""
            INSERT INTO historico_alteracoes (
                colaborador_id, data_hora, campo_alterado, valor_anterior, valor_novo, usuario_responsavel
            ) VALUES ({P},{P},{P},{P},{P},{P})
        """, (colaborador_id, agora, "Documento Anexado", None, f"{tipo_documento.strip()}: {nome_arquivo.strip()}", usuario))

        conn.commit()
        cursor.execute(f"SELECT id, colaborador_id, tipo_documento, nome_arquivo, mime_type, tamanho_bytes, observacao, enviado_por, criado_em FROM colaborador_documentos WHERE id = {P}", (doc_id,))
        doc = self._fetchone(cursor)
        conn.close()
        return doc

    def listar_documentos(self, colaborador_id: int) -> list:
        """Lista os documentos anexados do colaborador."""
        self.obter_por_id(colaborador_id)
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT id, colaborador_id, tipo_documento, nome_arquivo, mime_type, tamanho_bytes, observacao, enviado_por, criado_em FROM colaborador_documentos WHERE colaborador_id = {P} ORDER BY id DESC",
            (colaborador_id,)
        )
        docs = self._fetchall(cursor)
        conn.close()
        return docs

    def remover_documento(self, colaborador_id: int, doc_id: int, usuario: str = "Sistema/Administrador") -> bool:
        """Remove um documento anexado do colaborador."""
        self.obter_por_id(colaborador_id)
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(f"SELECT nome_arquivo FROM colaborador_documentos WHERE id = {P} AND colaborador_id = {P}", (doc_id, colaborador_id))
        row = cursor.fetchone()
        if not row:
            conn.close()
            raise RecursoNaoEncontradoException("Documento não encontrado para este colaborador.")
        nome_arq = row[0]
        cursor.execute(f"DELETE FROM colaborador_documentos WHERE id = {P} AND colaborador_id = {P}", (doc_id, colaborador_id))
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(f"""
            INSERT INTO historico_alteracoes (
                colaborador_id, data_hora, campo_alterado, valor_anterior, valor_novo, usuario_responsavel
            ) VALUES ({P},{P},{P},{P},{P},{P})
        """, (colaborador_id, agora, "Documento Removido", nome_arq, None, usuario))
        conn.commit()
        conn.close()
        return True

    def reativar(self, colaborador_id: int, usuario: str = "Sistema/Administrador") -> dict:
        """Reativacao logica com auditoria."""
        atual = self.obter_por_id(colaborador_id)
        if atual["situacao"] == "ativo":
            return atual

        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute(f"""
            UPDATE colaboradores SET situacao='ativo', atualizado_em={P} WHERE id={P}
        """, (agora, colaborador_id))

        cursor.execute(f"""
            INSERT INTO historico_alteracoes (
                colaborador_id, data_hora, campo_alterado,
                valor_anterior, valor_novo, usuario_responsavel
            ) VALUES ({P},{P},{P},{P},{P},{P})
        """, (colaborador_id, agora, "Situação do Vínculo", "inativo", "ativo", usuario))

        conn.commit()
        conn.close()
        return self.obter_por_id(colaborador_id)

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
    ) -> dict:
        """Anexa um documento cadastral ao colaborador com trilha de auditoria."""
        colab = self.obter_por_id(colaborador_id)
        if not (tipo_documento or "").strip() or not (nome_arquivo or "").strip():
            raise ValidacaoException({"documento": "Tipo de documento e nome do arquivo são obrigatórios."})

        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        empresa_id = colab.get("empresa_id") or "a0000000-0000-0000-0000-000000000001"

        sql_pg = """
            INSERT INTO colaborador_documentos (
                colaborador_id, empresa_id, tipo_documento, nome_arquivo,
                mime_type, tamanho_bytes, conteudo_base64, observacao, enviado_por, criado_em
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """
        sql_sqlite = """
            INSERT INTO colaborador_documentos (
                colaborador_id, empresa_id, tipo_documento, nome_arquivo,
                mime_type, tamanho_bytes, conteudo_base64, observacao, enviado_por, criado_em
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
        """
        doc_id = self._insert_id(cursor, conn, sql_pg, sql_sqlite, (
            colaborador_id, empresa_id, tipo_documento.strip(), nome_arquivo.strip(),
            (mime_type or "application/octet-stream").strip(), int(tamanho_bytes or 0),
            conteudo_base64 or "", (observacao or "").strip(), usuario, agora
        ))
        cursor.execute(f"""
            INSERT INTO historico_alteracoes (
                colaborador_id, data_hora, campo_alterado, valor_anterior, valor_novo, usuario_responsavel
            ) VALUES ({P},{P},{P},{P},{P},{P})
        """, (colaborador_id, agora, "Documento Anexado", None, f"{tipo_documento.strip()}: {nome_arquivo.strip()}", usuario))

        conn.commit()
        cursor.execute(f"SELECT id, colaborador_id, tipo_documento, nome_arquivo, mime_type, tamanho_bytes, observacao, enviado_por, criado_em FROM colaborador_documentos WHERE id = {P}", (doc_id,))
        doc = self._fetchone(cursor)
        conn.close()
        return doc

    def listar_documentos(self, colaborador_id: int) -> list:
        """Lista os documentos anexados do colaborador."""
        self.obter_por_id(colaborador_id)
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT id, colaborador_id, tipo_documento, nome_arquivo, mime_type, tamanho_bytes, observacao, enviado_por, criado_em FROM colaborador_documentos WHERE colaborador_id = {P} ORDER BY id DESC",
            (colaborador_id,)
        )
        docs = self._fetchall(cursor)
        conn.close()
        return docs

    def remover_documento(self, colaborador_id: int, doc_id: int, usuario: str = "Sistema/Administrador") -> bool:
        """Remove um documento anexado do colaborador."""
        self.obter_por_id(colaborador_id)
        P = self._ph()
        conn = self._conn()
        cursor = conn.cursor()
        cursor.execute(f"SELECT nome_arquivo FROM colaborador_documentos WHERE id = {P} AND colaborador_id = {P}", (doc_id, colaborador_id))
        row = cursor.fetchone()
        if not row:
            conn.close()
            raise RecursoNaoEncontradoException("Documento não encontrado para este colaborador.")
        nome_arq = row[0]
        cursor.execute(f"DELETE FROM colaborador_documentos WHERE id = {P} AND colaborador_id = {P}", (doc_id, colaborador_id))
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(f"""
            INSERT INTO historico_alteracoes (
                colaborador_id, data_hora, campo_alterado, valor_anterior, valor_novo, usuario_responsavel
            ) VALUES ({P},{P},{P},{P},{P},{P})
        """, (colaborador_id, agora, "Documento Removido", nome_arq, None, usuario))
        conn.commit()
        conn.close()
        return True
