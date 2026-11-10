import {
  BadRequestException,
  ConflictException,
  ForbiddenException,
  Injectable,
  NotFoundException,
} from '@nestjs/common';
import { ColaboradoresRepository } from './colaboradores.repository';
import { validarCpf, validarEmail, validarDataIso } from './validators';
import { QueryColaboradorDto } from './dto/query-colaborador.dto';
import { CreateColaboradorDto } from './dto/create-colaborador.dto';
import { UpdateColaboradorDto } from './dto/update-colaborador.dto';

export const EMPRESA_PADRAO_UUID = 'a0000000-0000-0000-0000-000000000001';

@Injectable()
export class ColaboradoresService {
  constructor(private readonly repository: ColaboradoresRepository) {}

  /**
   * Normaliza CPF removendo qualquer caractere não numérico
   */
  normalizarCpf(cpf: string): string {
    return String(cpf || '').replace(/\D/g, '');
  }

  /**
   * Aplica máscara de privacidade no CPF para listagens (RF-01, RF-07)
   */
  mascararCpf(cpf: string): string {
    const limpo = this.normalizarCpf(cpf);
    if (limpo.length === 11) {
      return `${limpo.slice(0, 3)}.***.***-${limpo.slice(9)}`;
    }
    return '***.***.***-**';
  }

  /**
   * Determina a lista de IDs de empresa que o usuário tem autorização para operar.
   * Retorna null quando o usuário tem permissão global (ex: administrador irrestrito).
   * Retorna array de strings de UUIDs quando o usuário é restrito a empresas específicas.
   */
  obterEmpresasAutorizadas(user?: any): string[] | null {
    if (!user) {
      return null;
    }

    // Administrador possui acesso global por padrão, a menos que possua restrição explícita em empresas_autorizadas
    if (user.perfil === 'administrador') {
      if (user.empresas_autorizadas && user.empresas_autorizadas !== '*') {
        try {
          const parsed = JSON.parse(user.empresas_autorizadas);
          if (Array.isArray(parsed) && parsed.length > 0) {
            return parsed.map((e) => String(e).trim());
          }
        } catch {
          const split = user.empresas_autorizadas
            .split(',')
            .map((e: string) => e.trim())
            .filter(Boolean);
          if (split.length > 0) return split;
        }
      }
      return null;
    }

    // Para analistas e operadores (usuários comuns), o escopo é estrito:
    if (user.empresas_autorizadas && user.empresas_autorizadas !== '*') {
      try {
        const parsed = JSON.parse(user.empresas_autorizadas);
        if (Array.isArray(parsed) && parsed.length > 0) {
          return parsed.map((e) => String(e).trim());
        }
      } catch {
        const split = user.empresas_autorizadas
          .split(',')
          .map((e: string) => e.trim())
          .filter(Boolean);
        if (split.length > 0) return split;
      }
    }

    // Usuário restrito à sua própria empresa
    const empresaUsuario = user.empresa_id || EMPRESA_PADRAO_UUID;
    return [empresaUsuario];
  }

  /**
   * Valida se a empresa informada está autorizada para o usuário
   */
  validarAcessoEmpresa(empresaId: string, user?: any, mensagemCustomizada?: string): void {
    const autorizadas = this.obterEmpresasAutorizadas(user);
    if (!autorizadas) {
      return; // Acesso global
    }

    if (!empresaId || !autorizadas.includes(empresaId)) {
      throw new ForbiddenException({
        sucesso: false,
        mensagem:
          mensagemCustomizada ||
          'Acesso negado: empresa fora do escopo autorizado do usuário.',
        codigo: 'EMPRESA_NAO_AUTORIZADA',
      });
    }
  }

  /**
   * Validações de domínio para criação
   */
  validarCriacao(dados: CreateColaboradorDto): void {
    const erros: string[] = [];

    const matricula = dados.matricula?.trim();
    if (!matricula) {
      erros.push('Matrícula é obrigatória.');
    }

    const nome = (dados.nomeCompleto || dados.nome_completo)?.trim();
    if (!nome) {
      erros.push('Nome completo é obrigatório.');
    }

    const cpfLimpo = this.normalizarCpf(dados.cpf);
    if (!cpfLimpo || !validarCpf(cpfLimpo)) {
      erros.push('CPF informado é inválido.');
    }

    const dataNasc = dados.dataNascimento || dados.data_nascimento;
    if (!dataNasc || !validarDataIso(dataNasc)) {
      erros.push('Data de nascimento inválida ou obrigatória (formato AAAA-MM-DD).');
    } else {
      const hoje = new Date().toISOString().split('T')[0];
      if (dataNasc > hoje) {
        erros.push('Data de nascimento não pode estar no futuro.');
      }
    }

    const dataAdm = dados.dataAdmissao || dados.data_admissao;
    if (dataAdm) {
      if (!validarDataIso(dataAdm)) {
        erros.push('Data de admissão inválida (formato AAAA-MM-DD).');
      } else if (dataNasc && dataAdm <= dataNasc) {
        erros.push('Data de admissão deve ser posterior à data de nascimento.');
      }
    }

    if (dados.email && !validarEmail(dados.email)) {
      erros.push('E-mail informado é inválido.');
    }

    if (erros.length > 0) {
      throw new BadRequestException({
        sucesso: false,
        mensagem: 'Inconsistência nos dados do colaborador.',
        erros,
      });
    }
  }

  async listar(
    query: QueryColaboradorDto,
    user?: any,
  ): Promise<{
    sucesso: boolean;
    total: number;
    dados: any[];
    data: any[];
    meta: { page: number; limit: number; total: number; totalPages: number };
  }> {
    const page = Math.max(1, Number(query.page) || 1);
    const limit = Math.max(1, Math.min(100, Number(query.limit) || 20));

    // Controle de escopo multiempresa (SPEC-03.1 Seção 3.1 & 3.2)
    const autorizadas = this.obterEmpresasAutorizadas(user);
    let empresaFiltro = query.empresaId;

    if (autorizadas !== null) {
      // Usuário com escopo restrito
      if (empresaFiltro) {
        // Se tentou passar empresaId por query, DEVE pertencer ao escopo autorizado
        if (!autorizadas.includes(empresaFiltro)) {
          throw new ForbiddenException({
            sucesso: false,
            mensagem: 'Acesso negado: empresa solicitada fora da sua abrangência autorizada.',
            codigo: 'EMPRESA_NAO_AUTORIZADA',
          });
        }
      } else {
        // Se não especificou empresaId, aplica estritamente a empresa autorizada do usuário
        empresaFiltro = autorizadas[0];
      }
    }

    const querySegura: QueryColaboradorDto = {
      ...query,
      empresaId: empresaFiltro,
    };

    const { colaboradores, total } = await this.repository.listarPaginado(querySegura);
    const totalPages = Math.ceil(total / limit) || 0;

    const data = colaboradores.map((c) => ({
      ...c,
      cpf_mascarado: this.mascararCpf(c.cpf),
      situacao: (c.situacao || 'ativo').toLowerCase(),
    }));

    return {
      sucesso: true,
      total,
      dados: data,
      data,
      meta: {
        page,
        limit,
        total,
        totalPages,
      },
    };
  }

  async obterPorId(id: number, user?: any): Promise<any> {
    const colab = await this.repository.buscarPorId(id);
    if (!colab) {
      throw new NotFoundException({
        sucesso: false,
        mensagem: `Colaborador #${id} não encontrado.`,
      });
    }

    // Proteção contra IDOR (SPEC-03.1 Seção 3.3)
    const autorizadas = this.obterEmpresasAutorizadas(user);
    if (autorizadas !== null && !autorizadas.includes(colab.empresa_id)) {
      // Retorna 404 para não vazar a existência de ID em outra empresa
      throw new NotFoundException({
        sucesso: false,
        mensagem: `Colaborador #${id} não encontrado.`,
      });
    }

    return {
      ...colab,
      cpf_mascarado: this.mascararCpf(colab.cpf),
      situacao: (colab.situacao || 'ativo').toLowerCase(),
    };
  }

  async criar(
    dados: CreateColaboradorDto,
    usuario = 'Sistema/Administrador',
    user?: any,
  ): Promise<any> {
    this.validarCriacao(dados);

    // Controle de escopo multiempresa no cadastro (SPEC-03.1 Seção 3.1 & 3.2)
    const autorizadas = this.obterEmpresasAutorizadas(user);
    let empresaId = dados.empresaId || dados.empresa_id;

    if (autorizadas !== null) {
      if (empresaId) {
        if (!autorizadas.includes(empresaId)) {
          throw new ForbiddenException({
            sucesso: false,
            mensagem:
              'Acesso negado: não é permitido cadastrar colaborador para empresa fora do seu escopo autorizado.',
            codigo: 'EMPRESA_NAO_AUTORIZADA',
          });
        }
      } else {
        empresaId = autorizadas[0];
      }
    } else {
      empresaId = empresaId || EMPRESA_PADRAO_UUID;
    }

    const cpfNormalizado = this.normalizarCpf(dados.cpf);
    const matricula = dados.matricula.trim();

    // 1. Prevenção de duplicidade de CPF na mesma empresa (RF-07, Seção 4.3)
    const existenteCpf = await this.repository.buscarPorCpf(cpfNormalizado, empresaId);
    if (existenteCpf) {
      throw new ConflictException({
        sucesso: false,
        mensagem: 'Já existe um colaborador cadastrado com este CPF nesta empresa.',
      });
    }

    // 2. Prevenção de duplicidade de Matrícula na mesma empresa (RF-08, Seção 4.3)
    const existenteMat = await this.repository.buscarPorMatricula(matricula, empresaId);
    if (existenteMat) {
      throw new ConflictException({
        sucesso: false,
        mensagem: 'Já existe um colaborador cadastrado com esta Matrícula nesta empresa.',
      });
    }

    const agora = new Date().toISOString().replace('T', ' ').slice(0, 19);
    const nomeCompleto = (dados.nomeCompleto || dados.nome_completo)!.trim();
    const dataNascimento = (dados.dataNascimento || dados.data_nascimento)!;
    const dataAdmissao = dados.dataAdmissao || dados.data_admissao || null;
    const salarioBase = dados.salarioBase !== undefined ? dados.salarioBase : dados.salario_base;

    const payloadFormatado = {
      empresa_id: empresaId,
      filial_id: dados.filialId || dados.filial_id || null,
      matricula,
      nome_completo: nomeCompleto,
      cpf: cpfNormalizado,
      data_nascimento: dataNascimento,
      sexo: dados.sexo || null,
      estado_civil: dados.estadoCivil || dados.estado_civil || null,
      email: dados.email?.trim() || null,
      telefone: dados.telefone?.trim() || null,
      celular: dados.celular?.trim() || null,
      cep: dados.cep?.trim() || null,
      logradouro: dados.logradouro?.trim() || null,
      numero: dados.numero?.trim() || null,
      complemento: dados.complemento?.trim() || null,
      bairro: dados.bairro?.trim() || null,
      cidade: dados.cidade?.trim() || null,
      uf: dados.uf?.trim() || null,
      departamento_id: dados.departamentoId || dados.departamento_id || null,
      cargo_id: dados.cargoId || dados.cargo_id || null,
      data_admissao: dataAdmissao,
      cargo: dados.cargo || dados.cargoId || 'Não Informado',
      setor: dados.setor || dados.departamentoId || 'Geral',
      salario_base: salarioBase !== undefined ? parseFloat(String(salarioBase)) : 0,
      situacao: (dados.situacao || 'ATIVO').toUpperCase(),
      observacoes: dados.observacoes || null,
      rg: dados.rg || null,
    };

    const novo = await this.repository.inserir(payloadFormatado, usuario, agora);

    // Dependentes
    if (Array.isArray(dados.dependentes) && dados.dependentes.length > 0) {
      await this.repository.inserirDependentes(novo.id, dados.dependentes);
    }

    // Histórico de auditoria (RF-11)
    await this.repository.inserirHistorico(
      novo.id,
      'CADASTRO',
      'colaborador',
      null,
      'Colaborador cadastrado no sistema',
      usuario,
      agora,
    );

    return this.obterPorId(novo.id, user);
  }

  async atualizar(
    id: number,
    dados: UpdateColaboradorDto,
    usuario = 'Sistema/Administrador',
    user?: any,
  ): Promise<any> {
    // 1. Valida existência e IDOR através do escopo do usuário autenticado
    const atual = await this.obterPorId(id, user);

    // 2. Proteção contra alteração indevida de empresaId no payload (SPEC-03.1 Seção 3.1 & 3.3)
    const payloadEmpresaId = dados.empresaId || dados.empresa_id;
    if (payloadEmpresaId && payloadEmpresaId !== atual.empresa_id) {
      const autorizadas = this.obterEmpresasAutorizadas(user);
      if (autorizadas !== null) {
        throw new ForbiddenException({
          sucesso: false,
          mensagem:
            'Acesso negado: não é permitido alterar empresaId para empresa fora do escopo autorizado.',
          codigo: 'EMPRESA_NAO_AUTORIZADA',
        });
      }
    }

    const empresaId = payloadEmpresaId || atual.empresa_id || EMPRESA_PADRAO_UUID;
    const agora = new Date().toISOString().replace('T', ' ').slice(0, 19);

    const camposParaAtualizar: Record<string, any> = {};

    // Valida e prepara CPF se enviado
    if (dados.cpf !== undefined) {
      const cpfLimpo = this.normalizarCpf(dados.cpf);
      if (!validarCpf(cpfLimpo)) {
        throw new BadRequestException({ sucesso: false, mensagem: 'CPF informado é inválido.' });
      }
      if (cpfLimpo !== atual.cpf) {
        const existente = await this.repository.buscarPorCpf(cpfLimpo, empresaId);
        if (existente && existente.id !== id) {
          throw new ConflictException({
            sucesso: false,
            mensagem: 'Já existe outro colaborador cadastrado com este CPF nesta empresa.',
          });
        }
        camposParaAtualizar['cpf'] = cpfLimpo;
        await this.repository.inserirHistorico(id, 'ALTERACAO', 'cpf', atual.cpf, cpfLimpo, usuario, agora);
      }
    }

    // Valida e prepara Matrícula se enviada
    if (dados.matricula !== undefined) {
      const mat = dados.matricula.trim();
      if (!mat) {
        throw new BadRequestException({ sucesso: false, mensagem: 'Matrícula não pode ser vazia.' });
      }
      if (mat !== atual.matricula) {
        const existente = await this.repository.buscarPorMatricula(mat, empresaId);
        if (existente && existente.id !== id) {
          throw new ConflictException({
            sucesso: false,
            mensagem: 'Já existe outro colaborador cadastrado com esta Matrícula nesta empresa.',
          });
        }
        camposParaAtualizar['matricula'] = mat;
        await this.repository.inserirHistorico(id, 'ALTERACAO', 'matricula', atual.matricula, mat, usuario, agora);
      }
    }

    // Mapeamento e auditoria de outros campos
    const mapaCampos: [string, any][] = [
      ['nome_completo', dados.nomeCompleto || dados.nome_completo],
      ['data_nascimento', dados.dataNascimento || dados.data_nascimento],
      ['sexo', dados.sexo],
      ['estado_civil', dados.estadoCivil || dados.estado_civil],
      ['email', dados.email],
      ['telefone', dados.telefone],
      ['celular', dados.celular],
      ['cep', dados.cep],
      ['logradouro', dados.logradouro],
      ['numero', dados.numero],
      ['complemento', dados.complemento],
      ['bairro', dados.bairro],
      ['cidade', dados.cidade],
      ['uf', dados.uf],
      ['departamento_id', dados.departamentoId || dados.departamento_id],
      ['cargo_id', dados.cargoId || dados.cargo_id],
      ['cargo', dados.cargo || dados.cargoId],
      ['setor', dados.setor || dados.departamentoId],
      ['data_admissao', dados.dataAdmissao || dados.data_admissao],
      ['observacoes', dados.observacoes],
      ['rg', dados.rg],
      ['situacao', dados.situacao ? dados.situacao.toUpperCase() : undefined],
    ];

    for (const [col, val] of mapaCampos) {
      if (val !== undefined && val !== null) {
        const strVal = String(val).trim();
        const strAnt = String(atual[col] ?? '').trim();
        if (strVal !== strAnt) {
          camposParaAtualizar[col] = strVal;
          await this.repository.inserirHistorico(id, 'ALTERACAO', col, strAnt, strVal, usuario, agora);
        }
      }
    }

    if (dados.salarioBase !== undefined || dados.salario_base !== undefined) {
      const sal = dados.salarioBase !== undefined ? dados.salarioBase : dados.salario_base;
      const numSal = parseFloat(String(sal));
      if (!isNaN(numSal) && numSal !== parseFloat(String(atual.salario_base || 0))) {
        camposParaAtualizar['salario_base'] = numSal;
        await this.repository.inserirHistorico(
          id,
          'ALTERACAO',
          'salario_base',
          String(atual.salario_base),
          String(numSal),
          usuario,
          agora,
        );
      }
    }

    camposParaAtualizar['atualizado_por'] = usuario;
    await this.repository.atualizar(id, camposParaAtualizar, agora);

    return this.obterPorId(id, user);
  }

  async inativar(id: number, motivo = '', usuario = 'Sistema/Administrador', user?: any): Promise<any> {
    // 1. Valida existência e IDOR
    const atual = await this.obterPorId(id, user);
    const agora = new Date().toISOString().replace('T', ' ').slice(0, 19);

    await this.repository.inativar(id, usuario, agora);

    await this.repository.inserirHistorico(
      id,
      'INATIVACAO',
      'situacao',
      atual.situacao,
      'INATIVO',
      `${usuario} (Motivo: ${motivo || 'Confirmação do gestor'})`,
      agora,
    );

    return this.obterPorId(id, user);
  }

  async reativar(id: number, usuario = 'Sistema/Administrador', user?: any): Promise<any> {
    const atual = await this.obterPorId(id, user);
    const agora = new Date().toISOString().replace('T', ' ').slice(0, 19);

    await this.repository.atualizar(id, { situacao: 'ativo', atualizado_por: usuario }, agora);

    await this.repository.inserirHistorico(
      id,
      'REATIVACAO',
      'situacao',
      atual.situacao,
      'ativo',
      usuario,
      agora,
    );

    return this.obterPorId(id, user);
  }

  async obterHistorico(id: number, user?: any): Promise<any[]> {
    await this.obterPorId(id, user);
    return this.repository.buscarHistorico(id);
  }

  async obterMetricas(user?: any): Promise<any> {
    const autorizadas = this.obterEmpresasAutorizadas(user);
    const empresaId = autorizadas !== null ? autorizadas[0] : undefined;
    return this.repository.obterMetricas(empresaId);
  }
}
