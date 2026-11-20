"""
Módulo de Validações — Cadastro de Colaboradores
Atende aos requisitos de validação RF-02 e Critérios de Aceitação CA-02, CA-03.
"""
import os
import re
from datetime import date, datetime

CAMPOS_OBRIGATORIOS = [
    ("nome_completo", "Nome Completo"),
    ("cpf", "CPF"),
    ("data_nascimento", "Data de Nascimento"),
    ("email", "E-mail"),
    ("matricula", "Matrícula"),
    ("data_admissao", "Data de Admissão"),
    ("cargo", "Cargo"),
    ("setor", "Setor"),
    ("salario_base", "Salário-base"),
]

PARENTESCOS_VALIDOS = [
    "Filho(a)",
    "Cônjuge/Companheiro(a)",
    "Pai/Mãe",
    "Enteado(a)",
    "Irmão(ã)",
    "Outro"
]

SITUACOES_COLABORADOR_VALIDAS = ("ativo", "inativo", "afastado", "ferias", "desligado")

def normalizar_pis(pis: str) -> str:
    """Remove caracteres não numéricos do PIS/PASEP/NIT."""
    if not pis:
        return ""
    return re.sub(r"\D", "", str(pis))

def validar_pis_pasep(pis: str) -> bool:
    """Valida dígito verificador do PIS/PASEP/NIT (11 dígitos)."""
    numeros = normalizar_pis(pis)
    if len(numeros) != 11 or numeros == numeros[0] * 11:
        return False
    pesos = [3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma = sum(int(numeros[i]) * pesos[i] for i in range(10))
    resto = soma % 11
    dv = 0 if (11 - resto) in (10, 11) else (11 - resto)
    return dv == int(numeros[10])

def formatar_pis_pasep(pis: str) -> str:
    """Formata PIS/PASEP/NIT no padrão 000.00000.00-0."""
    n = normalizar_pis(pis)
    if len(n) == 11:
        return f"{n[0:3]}.{n[3:8]}.{n[8:10]}-{n[10]}"
    return pis

def normalizar_cpf(cpf: str) -> str:
    """Remove caracteres não numéricos do CPF."""
    if not cpf:
        return ""
    return re.sub(r"\D", "", str(cpf))

def validar_cpf(cpf: str) -> bool:
    """
    Validação de CPF segundo algoritmo oficial da Receita Federal (dígitos verificadores).
    Retorna True se válido, False caso contrário.
    """
    numeros = normalizar_cpf(cpf)
    if len(numeros) != 11:
        return False

    # MODO TEMPORARIO DE APRESENTACAO:
    # com RH2_ALLOW_FAKE_CPFS=1, aceita qualquer sequencia de 11 digitos.
    # A unicidade do CPF no banco continua obrigatoria.
    if os.environ.get("RH2_ALLOW_FAKE_CPFS") == "1":
        return True

    # Rejeita CPFs com todos os dígitos iguais (ex: 111.111.111-11)
    if numeros == numeros[0] * 11:
        return False

    # Cálculo do primeiro dígito verificador
    soma_1 = sum(int(numeros[i]) * (10 - i) for i in range(9))
    resto_1 = (soma_1 * 10) % 11
    digito_1 = 0 if resto_1 == 10 else resto_1
    if digito_1 != int(numeros[9]):
        return False

    # Cálculo do segundo dígito verificador
    soma_2 = sum(int(numeros[i]) * (11 - i) for i in range(10))
    resto_2 = (soma_2 * 10) % 11
    digito_2 = 0 if resto_2 == 10 else resto_2
    if digito_2 != int(numeros[10]):
        return False

    return True

def formatar_cpf(cpf: str) -> str:
    """Formata CPF no padrão 000.000.000-00."""
    numeros = normalizar_cpf(cpf)
    if len(numeros) == 11:
        return f"{numeros[0:3]}.{numeros[3:6]}.{numeros[6:9]}-{numeros[9:11]}"
    return cpf

def validar_email(email: str) -> bool:
    """Valida formato de e-mail usando expressão regular padrão."""
    if not email or not isinstance(email, str):
        return False
    regex = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    return bool(re.match(regex, email.strip()))

def converter_para_data(data_str: str):
    """Converte string YYYY-MM-DD ou DD/MM/YYYY para objeto date."""
    if not data_str:
        return None
    data_str = str(data_str).strip()
    formatos = ["%Y-%m-%d", "%d/%m/%Y"]
    for formato in formatos:
        try:
            return datetime.strptime(data_str, formato).date()
        except ValueError:
            continue
    return None

def validar_data_nascimento(data_str: str) -> tuple[bool, str]:
    """
    Valida data de nascimento.
    Regra: Data válida no passado, idade mínima de 14 anos (aprendiz) e menor de 120 anos.
    """
    dt = converter_para_data(data_str)
    if not dt:
        return False, "Data de nascimento inválida. Use o formato AAAA-MM-DD ou DD/MM/AAAA."

    hoje = date.today()
    if dt > hoje:
        return False, "A data de nascimento não pode ser futura."

    idade = hoje.year - dt.year - ((hoje.month, hoje.day) < (dt.month, dt.day))
    if idade < 14:
        return False, "O colaborador deve ter no mínimo 14 anos (conforme legislação vigente para jovem aprendiz)."
    if idade > 120:
        return False, "Data de nascimento inconsistente (idade superior a 120 anos)."

    return True, ""

def validar_data_admissao(data_str: str, data_nasc_str: str = None) -> tuple[bool, str]:
    """
    Valida data de admissão.
    Regra: Data válida e cronologicamente posterior à data de nascimento em ao menos 14 anos.
    """
    dt_adm = converter_para_data(data_str)
    if not dt_adm:
        return False, "Data de admissão inválida. Use o formato AAAA-MM-DD ou DD/MM/AAAA."

    if data_nasc_str:
        dt_nasc = converter_para_data(data_nasc_str)
        if dt_nasc and dt_adm <= dt_nasc:
            return False, "A data de admissão deve ser posterior à data de nascimento."
        if dt_nasc:
            diff_anos = dt_adm.year - dt_nasc.year - ((dt_adm.month, dt_adm.day) < (dt_nasc.month, dt_nasc.day))
            if diff_anos < 14:
                return False, "A data de admissão deve respeitar a idade mínima legal de 14 anos do colaborador."

    return True, ""

def validar_salario_base(valor) -> tuple[bool, float, str]:
    """
    Valida salário-base.
    Permite números ou strings formatadas (ex: 2500, '2500.00', 'R$ 2.500,00').
    """
    if valor is None or valor == "":
        return False, 0.0, "Salário-base é obrigatório."

    if isinstance(valor, (int, float)):
        val_float = float(valor)
    else:
        # Limpar símbolos de moeda e formatação brasileira
        s = str(valor).replace("R$", "").strip()
        s = s.replace(".", "").replace(",", ".")
        try:
            val_float = float(s)
        except ValueError:
            return False, 0.0, "Salário-base deve ser um valor numérico válido."

    if val_float <= 0:
        return False, 0.0, "Salário-base deve ser maior que zero."

    return True, round(val_float, 2), ""

def validar_dependente(dependente: dict) -> tuple[bool, list[str]]:
    """Valida um registro de dependente."""
    erros = []
    nome = (dependente.get("nome") or "").strip()
    if not nome:
        erros.append("Nome do dependente é obrigatório.")
    elif len(nome) < 3:
        erros.append("Nome do dependente deve ter no mínimo 3 caracteres.")

    parentesco = (dependente.get("parentesco") or "").strip()
    if not parentesco:
        erros.append("Grau de parentesco é obrigatório.")

    cpf_dep = dependente.get("cpf")
    if cpf_dep:
        cpf_limpo = normalizar_cpf(cpf_dep)
        if cpf_limpo and not validar_cpf(cpf_limpo):
            erros.append(f"CPF do dependente '{nome or 'sem nome'}' é inválido.")

    return len(erros) == 0, erros

def validar_formulario_colaborador(dados: dict, is_edicao: bool = False) -> tuple[bool, dict, dict]:
    """
    Valida todos os campos do formulário de colaborador.
    Retorna: (is_valido, erros_dict, dados_sanitizados)
    """
    erros = {}
    sanitizado = {}

    # 1. Campos obrigatórios (se auto_gerar_matricula=True, matricula será gerada pelo serviço)
    auto_mat = bool(dados.get("auto_gerar_matricula"))
    for campo, rotulo in CAMPOS_OBRIGATORIOS:
        if campo == "matricula" and auto_mat:
            continue
        val = dados.get(campo)
        if val is None or str(val).strip() == "":
            erros[campo] = f"O campo {rotulo} é obrigatório."

    # 2. Nome Completo
    nome = (dados.get("nome_completo") or "").strip()
    if nome:
        if len(nome) < 3:
            erros["nome_completo"] = "O nome completo deve conter no mínimo 3 caracteres."
        elif not re.search(r"\s+", nome):
            erros["nome_completo"] = "Informe o nome e ao menos um sobrenome."
        sanitizado["nome_completo"] = nome

    # 3. CPF
    cpf = dados.get("cpf")
    if cpf:
        cpf_norm = normalizar_cpf(cpf)
        if not validar_cpf(cpf_norm):
            erros["cpf"] = "CPF inválido. Verifique os dígitos informados."
        else:
            sanitizado["cpf"] = formatar_cpf(cpf_norm)

    # 4. RG, PIS/PASEP/NIT, Sexo, Estado Civil (Opcionais, sanitizados se fornecidos)
    rg = (dados.get("rg") or "").strip()
    sanitizado["rg"] = rg

    pis_raw = (dados.get("pis_pasep") or "").strip()
    if pis_raw:
        pis_norm = normalizar_pis(pis_raw)
        if len(pis_norm) != 11 or not validar_pis_pasep(pis_norm):
            erros["pis_pasep"] = "PIS/PASEP/NIT inválido. Informe 11 dígitos válidos."
        else:
            sanitizado["pis_pasep"] = formatar_pis_pasep(pis_norm)
    else:
        sanitizado["pis_pasep"] = ""

    sanitizado["sexo"] = (dados.get("sexo") or "").strip()
    sanitizado["estado_civil"] = (dados.get("estado_civil") or "").strip()

    # 5. Data de Nascimento
    dt_nasc = dados.get("data_nascimento")
    if dt_nasc:
        ok, msg = validar_data_nascimento(dt_nasc)
        if not ok:
            erros["data_nascimento"] = msg
        else:
            dt_obj = converter_para_data(dt_nasc)
            sanitizado["data_nascimento"] = dt_obj.strftime("%Y-%m-%d")

    # 6. E-mail
    email = (dados.get("email") or "").strip().lower()
    if email:
        if not validar_email(email):
            erros["email"] = "E-mail com formato inválido (exemplo: nome@empresa.com.br)."
        else:
            sanitizado["email"] = email

    # 7. Telefone (Opcional)
    telefone = (dados.get("telefone") or "").strip()
    sanitizado["telefone"] = telefone

    # 8. Endereço
    sanitizado["logradouro"] = (dados.get("logradouro") or "").strip()
    sanitizado["numero"] = (dados.get("numero") or "").strip()
    sanitizado["bairro"] = (dados.get("bairro") or "").strip()
    sanitizado["cidade"] = (dados.get("cidade") or "").strip()
    sanitizado["uf"] = (dados.get("uf") or "").strip().upper()
    sanitizado["cep"] = (dados.get("cep") or "").strip()

    # 9. Matrícula
    matricula = (dados.get("matricula") or "").strip()
    if matricula:
        if len(matricula) < 2:
            erros["matricula"] = "A matrícula deve conter no mínimo 2 caracteres."
        sanitizado["matricula"] = matricula

    # 10. Data de Admissão
    dt_adm = dados.get("data_admissao")
    if dt_adm:
        ok, msg = validar_data_admissao(dt_adm, sanitizado.get("data_nascimento"))
        if not ok:
            erros["data_admissao"] = msg
        else:
            dt_adm_obj = converter_para_data(dt_adm)
            sanitizado["data_admissao"] = dt_adm_obj.strftime("%Y-%m-%d")

    # 11. Cargo, Setor e Dados Contratuais Complementares
    cargo = (dados.get("cargo") or "").strip()
    if cargo:
        sanitizado["cargo"] = cargo

    setor = (dados.get("setor") or "").strip()
    if setor:
        sanitizado["setor"] = setor

    sanitizado["departamento"] = (dados.get("departamento") or setor or "").strip()
    sanitizado["centro_custo"] = (dados.get("centro_custo") or "").strip()
    sanitizado["tipo_contrato"] = (dados.get("tipo_contrato") or "CLT").strip()
    sanitizado["jornada_trabalho"] = (dados.get("jornada_trabalho") or "44h semanais").strip()
    ch_raw = dados.get("carga_horaria_mensal", 220.0)
    try:
        ch_val = float(ch_raw) if ch_raw not in (None, "") else 220.0
        if ch_val <= 0 or ch_val > 360:
            erros["carga_horaria_mensal"] = "Carga horária mensal deve estar entre 1 e 360 horas."
        else:
            sanitizado["carga_horaria_mensal"] = round(ch_val, 2)
    except (ValueError, TypeError):
        erros["carga_horaria_mensal"] = "Carga horária mensal inválida."

    # 12. Salário-base
    salario = dados.get("salario_base")
    if salario is not None and str(salario).strip() != "":
        ok, val_salario, msg = validar_salario_base(salario)
        if not ok:
            erros["salario_base"] = msg
        else:
            sanitizado["salario_base"] = val_salario

    # 13. Situação do vínculo
    situacao = str(dados.get("situacao") or "ativo").strip().lower()
    if situacao not in SITUACOES_COLABORADOR_VALIDAS:
        situacao = "ativo"
    sanitizado["situacao"] = situacao

    # 14. Dependentes
    dependentes_sanitizados = []
    dependentes_raw = dados.get("dependentes") or []
    if isinstance(dependentes_raw, list):
        erros_deps = []
        for i, dep in enumerate(dependentes_raw):
            ok_dep, errs = validar_dependente(dep)
            if not ok_dep:
                erros_deps.extend([f"Dependente {i+1}: {e}" for e in errs])
            else:
                cpf_dep_limpo = normalizar_cpf(dep.get("cpf", ""))
                dt_nasc_dep = ""
                if dep.get("data_nascimento"):
                    dt_obj = converter_para_data(dep.get("data_nascimento"))
                    if dt_obj:
                        dt_nasc_dep = dt_obj.strftime("%Y-%m-%d")
                    else:
                        erros_deps.append(f"Dependente {i+1}: Data de nascimento inválida.")
                eh_irrf = 1 if dep.get("eh_dependente_irrf", 1) in (1, True, "1", "true", "True") else 0
                eh_sf = 1 if dep.get("eh_elegivel_salario_familia", 0) in (1, True, "1", "true", "True") else 0
                dependentes_sanitizados.append({
                    "nome": dep.get("nome", "").strip(),
                    "cpf": formatar_cpf(cpf_dep_limpo) if cpf_dep_limpo else "",
                    "parentesco": dep.get("parentesco", "").strip(),
                    "data_nascimento": dt_nasc_dep,
                    "eh_dependente_irrf": eh_irrf,
                    "eh_elegivel_salario_familia": eh_sf,
                })
        if erros_deps:
            erros["dependentes"] = erros_deps
    sanitizado["dependentes"] = dependentes_sanitizados

    return len(erros) == 0, erros, sanitizado
