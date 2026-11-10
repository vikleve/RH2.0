import {
  BadRequestException,
  ConflictException,
  Injectable,
  NotFoundException,
} from '@nestjs/common';
import { DatabaseService } from '../../database/database.service';
import { validarCpf, validarEmail, validarDataIso } from './validators';

@Injectable()
export class ColaboradoresService {
  constructor(private readonly db: DatabaseService) {}

  validarDadosColaborador(dados: any, ignorarId?: number): void {
    const erros: string[] = [];

    if (!dados.matricula || !String(dados.matricula).trim()) {
      erros.push('Matrícula é obrigatória.');
    }
    if (!dados.nome_completo || !String(dados.nome_completo).trim()) {
      erros.push('Nome completo é obrigatório.');
    }
    if (!dados.cpf || !validarCpf(dados.cpf)) {
      erros.push('CPF informado é inválido.');
    }
    if (!dados.data_nascimento || !validarDataIso(dados.data_nascimento)) {
      erros.push('Data de nascimento inválida.');
    }
    if (!dados.data_admissao || !validarDataIso(dados.data_admissao)) {
      erros.push('Data de admissão inválida.');
    }
    if (dados.data_nascimento && dados.data_admissao) {
      if (dados.data_admissao <= dados.data_nascimento) {
        erros.push('Data de admissão deve ser posterior à data de nascimento.');
      }
      const hoje = new Date().toISOString().split('T')[0];
      if (dados.data_nascimento > hoje) {
        erros.push('Data de nascimento não pode estar no futuro.');
      }
    }
    if (!dados.email || !validarEmail(dados.email)) {
      erros.push('E-mail informado é inválido.');
    }
    if (!dados.cargo || !String(dados.cargo).trim()) {
      erros.push('Cargo é obrigatório.');
    }
    if (!dados.setor || !String(dados.setor).trim()) {
      erros.push('Setor é obrigatório.');
    }
    const salario = parseFloat(dados.salario_base);
    if (isNaN(salario) || salario <= 0) {
      erros.push('Salário base deve ser um valor numérico positivo.');
    }

    if (erros.length > 0) {
      throw new BadRequestException({
        sucesso: false,
        mensagem: 'Existem inconsistências nos dados informados.',
        erros,
      });
    }
  }

  async listar(filtros: { termo?: string; situacao?: string; setor?: string }): Promise<any[]> {
    let sql = `SELECT * FROM colaboradores WHERE 1=1`;
    const params: any[] = [];

    if (filtros.situacao && filtros.situacao !== 'todos') {
      params.push(filtros.situacao);
      sql += ` AND situacao = $${params.length}`;
    }
    if (filtros.setor) {
      params.push(filtros.setor);
      sql += ` AND setor = $${params.length}`;
    }
    if (filtros.termo) {
      params.push(`%${filtros.termo}%`);
      const p = `$${params.length}`;
      sql += ` AND (LOWER(nome_completo) LIKE LOWER(${p}) OR LOWER(cpf) LIKE LOWER(${p}) OR LOWER(matricula) LIKE LOWER(${p}))`;
    }

    sql += ` ORDER BY id ASC`;
    const res = await this.db.query(sql, params);
    return res.rows;
  }

  async obterPorId(id: number): Promise<any> {
    const res = await this.db.query(`SELECT * FROM colaboradores WHERE id = $1`, [id]);
    if (res.rows.length === 0) {
      throw new NotFoundException({ sucesso: false, mensagem: 'Colaborador não encontrado.' });
    }
    const colab = res.rows[0];
    const depRes = await this.db.query(`SELECT * FROM dependentes WHERE colaborador_id = $1`, [id]);
    colab.dependentes = depRes.rows;
    return colab;
  }

  async criar(dados: any, usuario = 'Sistema/Administrador'): Promise<any> {
    this.validarDadosColaborador(dados);

    // Unicidade de CPF e Matrícula
    const checkCpf = await this.db.query(`SELECT id FROM colaboradores WHERE cpf = $1`, [dados.cpf]);
    if (checkCpf.rows.length > 0) {
      throw new ConflictException({ sucesso: false, mensagem: 'Já existe um colaborador cadastrado com este CPF.' });
    }
    const checkMat = await this.db.query(`SELECT id FROM colaboradores WHERE matricula = $1`, [dados.matricula]);
    if (checkMat.rows.length > 0) {
      throw new ConflictException({ sucesso: false, mensagem: 'Já existe um colaborador cadastrado com esta Matrícula.' });
    }

    const agora = new Date().toISOString().replace('T', ' ').slice(0, 19);
    const res = await this.db.query(
      `INSERT INTO colaboradores (
        matricula, nome_completo, cpf, rg, data_nascimento, telefone, email,
        logradouro, numero, bairro, cidade, uf, cep, data_admissao,
        cargo, setor, salario_base, situacao, criado_em, atualizado_em
      ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,'ativo',$18,$18)
      RETURNING *`,
      [
        dados.matricula,
        dados.nome_completo,
        dados.cpf,
        dados.rg || '',
        dados.data_nascimento,
        dados.telefone || '',
        dados.email,
        dados.logradouro || '',
        dados.numero || '',
        dados.bairro || '',
        dados.cidade || '',
        dados.uf || '',
        dados.cep || '',
        dados.data_admissao,
        dados.cargo,
        dados.setor,
        parseFloat(dados.salario_base),
        agora,
      ],
    );

    const novo = res.rows[0];

    // Dependentes
    if (Array.isArray(dados.dependentes)) {
      for (const d of dados.dependentes) {
        if (d.nome && d.parentesco) {
          await this.db.query(
            `INSERT INTO dependentes (colaborador_id, nome, cpf, parentesco) VALUES ($1, $2, $3, $4)`,
            [novo.id, d.nome, d.cpf || '', d.parentesco],
          );
        }
      }
    }

    // Histórico
    await this.db.query(
      `INSERT INTO historico_alteracoes (colaborador_id, data_hora, campo_alterado, valor_anterior, valor_novo, usuario_responsavel)
       VALUES ($1, $2, 'cadastro_inicial', NULL, 'Colaborador cadastrado', $3)`,
      [novo.id, agora, usuario],
    );

    return this.obterPorId(novo.id);
  }

  async atualizar(id: number, dados: any, usuario = 'Sistema/Administrador'): Promise<any> {
    const atual = await this.obterPorId(id);
    this.validarDadosColaborador(dados, id);

    // Unicidade de CPF e Matrícula desconsiderando o próprio id
    const checkCpf = await this.db.query(`SELECT id FROM colaboradores WHERE cpf = $1 AND id <> $2`, [dados.cpf, id]);
    if (checkCpf.rows.length > 0) {
      throw new ConflictException({ sucesso: false, mensagem: 'Já existe outro colaborador cadastrado com este CPF.' });
    }
    const checkMat = await this.db.query(`SELECT id FROM colaboradores WHERE matricula = $1 AND id <> $2`, [dados.matricula, id]);
    if (checkMat.rows.length > 0) {
      throw new ConflictException({ sucesso: false, mensagem: 'Já existe outro colaborador cadastrado com esta Matrícula.' });
    }

    const agora = new Date().toISOString().replace('T', ' ').slice(0, 19);

    // Registrar alterações no histórico
    const campos = ['nome_completo', 'email', 'telefone', 'cargo', 'setor', 'salario_base'];
    for (const c of campos) {
      const valAnt = String(atual[c] ?? '');
      const valNovo = String(dados[c] ?? '');
      if (valAnt !== valNovo) {
        await this.db.query(
          `INSERT INTO historico_alteracoes (colaborador_id, data_hora, campo_alterado, valor_anterior, valor_novo, usuario_responsavel)
           VALUES ($1, $2, $3, $4, $5, $6)`,
          [id, agora, c, valAnt, valNovo, usuario],
        );
      }
    }

    await this.db.query(
      `UPDATE colaboradores SET
        matricula = $1, nome_completo = $2, cpf = $3, rg = $4, data_nascimento = $5,
        telefone = $6, email = $7, logradouro = $8, numero = $9, bairro = $10,
        cidade = $11, uf = $12, cep = $13, data_admissao = $14, cargo = $15,
        setor = $16, salario_base = $17, atualizado_em = $18
       WHERE id = $19`,
      [
        dados.matricula,
        dados.nome_completo,
        dados.cpf,
        dados.rg || '',
        dados.data_nascimento,
        dados.telefone || '',
        dados.email,
        dados.logradouro || '',
        dados.numero || '',
        dados.bairro || '',
        dados.cidade || '',
        dados.uf || '',
        dados.cep || '',
        dados.data_admissao,
        dados.cargo,
        dados.setor,
        parseFloat(dados.salario_base),
        agora,
        id,
      ],
    );

    return this.obterPorId(id);
  }

  async inativar(id: number, motivo = '', usuario = 'Sistema/Administrador'): Promise<any> {
    await this.obterPorId(id);
    const agora = new Date().toISOString().replace('T', ' ').slice(0, 19);
    await this.db.query(`UPDATE colaboradores SET situacao = 'inativo', atualizado_em = $1 WHERE id = $2`, [agora, id]);
    await this.db.query(
      `INSERT INTO historico_alteracoes (colaborador_id, data_hora, campo_alterado, valor_anterior, valor_novo, usuario_responsavel)
       VALUES ($1, $2, 'situacao', 'ativo', 'inativo', $3)`,
      [id, agora, `${usuario} (Motivo: ${motivo || 'Não informado'})`],
    );
    return this.obterPorId(id);
  }

  async reativar(id: number, usuario = 'Sistema/Administrador'): Promise<any> {
    await this.obterPorId(id);
    const agora = new Date().toISOString().replace('T', ' ').slice(0, 19);
    await this.db.query(`UPDATE colaboradores SET situacao = 'ativo', atualizado_em = $1 WHERE id = $2`, [agora, id]);
    await this.db.query(
      `INSERT INTO historico_alteracoes (colaborador_id, data_hora, campo_alterado, valor_anterior, valor_novo, usuario_responsavel)
       VALUES ($1, $2, 'situacao', 'inativo', 'ativo', $3)`,
      [id, agora, usuario],
    );
    return this.obterPorId(id);
  }

  async obterHistorico(id: number): Promise<any[]> {
    await this.obterPorId(id);
    const res = await this.db.query(
      `SELECT * FROM historico_alteracoes WHERE colaborador_id = $1 ORDER BY id DESC`,
      [id],
    );
    return res.rows;
  }

  async obterMetricas(): Promise<any> {
    const resAtivos = await this.db.query(`SELECT COUNT(*) as total FROM colaboradores WHERE situacao = 'ativo'`);
    const resInativos = await this.db.query(`SELECT COUNT(*) as total FROM colaboradores WHERE situacao = 'inativo'`);
    const resDep = await this.db.query(`SELECT COUNT(*) as total FROM dependentes`);
    const resSetores = await this.db.query(
      `SELECT setor, COUNT(*) as qtd FROM colaboradores GROUP BY setor ORDER BY qtd DESC`,
    );

    return {
      total_ativos: parseInt(resAtivos.rows[0]?.total || 0, 10),
      total_inativos: parseInt(resInativos.rows[0]?.total || 0, 10),
      total_dependentes: parseInt(resDep.rows[0]?.total || 0, 10),
      por_setor: resSetores.rows,
    };
  }
}

