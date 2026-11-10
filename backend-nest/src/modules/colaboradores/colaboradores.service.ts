import {
  BadRequestException,
  ConflictException,
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
  ): Promise<{
    sucesso: boolean;
    total: number;
    dados: any[];
    data: any[];
    meta: { page: number; limit: number; total: number; totalPages: number };
  }> {
    const page = Math.max(1, Number(query.page) || 1);
    const limit = Math.max(1, Math.min(100, Number(query.limit) || 20));

    const { colaboradores, total } = await this.repository.listarPaginado(query);
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

  async obterPorId(id: number): Promise<any> {
    const colab = await this.repository.buscarPorId(id);
    if (!colab) {
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

  async criar(dados: CreateColaboradorDto, usuario = 'Sistema/Administrador'): Promise<any> {
    this.validarCriacao(dados);

    const cpfNormalizado = this.normalizarCpf(dados.cpf);
    const empresaId = dados.empresaId || dados.empresa_id || EMPRESA_PADRAO_UUID;
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

    return this.obterPorId(novo.id);
  }

  async atualizar(
    id: number,
    dados: UpdateColaboradorDto,
    usuario = 'Sistema/Administrador',
  ): Promise<any> {
    const atual = await this.obterPorId(id);
    const empresaId = dados.empresaId || dados.empresa_id || atual.empresa_id || EMPRESA_PADRAO_UUID;
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

    return this.obterPorId(id);
  }

  async inativar(id: number, motivo = '', usuario = 'Sistema/Administrador'): Promise<any> {
    const atual = await this.obterPorId(id);
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

    return this.obterPorId(id);
  }

  async reativar(id: number, usuario = 'Sistema/Administrador'): Promise<any> {
    const atual = await this.obterPorId(id);
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

    return this.obterPorId(id);
  }

  async obterHistorico(id: number): Promise<any[]> {
    await this.obterPorId(id);
    return this.repository.buscarHistorico(id);
  }

  async obterMetricas(): Promise<any> {
    return this.repository.obterMetricas();
  }
}
