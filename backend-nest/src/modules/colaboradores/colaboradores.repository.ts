import { Injectable } from '@nestjs/common';
import { DatabaseService } from '../../database/database.service';
import { QueryColaboradorDto } from './dto/query-colaborador.dto';

@Injectable()
export class ColaboradoresRepository {
  constructor(private readonly db: DatabaseService) {}

  async buscarPorId(id: number): Promise<any | null> {
    const res = await this.db.query(`SELECT * FROM colaboradores WHERE id = $1`, [id]);
    if (res.rows.length === 0) return null;
    const colab = res.rows[0];

    const depRes = await this.db.query(
      `SELECT * FROM dependentes WHERE colaborador_id = $1`,
      [id],
    );
    colab.dependentes = depRes.rows;
    return colab;
  }

  async buscarPorCpf(cpf: string, empresaId?: string): Promise<any | null> {
    if (empresaId) {
      const res = await this.db.query(
        `SELECT * FROM colaboradores WHERE cpf = $1 AND empresa_id = $2`,
        [cpf, empresaId],
      );
      return res.rows[0] || null;
    }
    const res = await this.db.query(`SELECT * FROM colaboradores WHERE cpf = $1`, [cpf]);
    return res.rows[0] || null;
  }

  async buscarPorMatricula(matricula: string, empresaId?: string): Promise<any | null> {
    if (empresaId) {
      const res = await this.db.query(
        `SELECT * FROM colaboradores WHERE matricula = $1 AND empresa_id = $2`,
        [matricula, empresaId],
      );
      return res.rows[0] || null;
    }
    const res = await this.db.query(`SELECT * FROM colaboradores WHERE matricula = $1`, [matricula]);
    return res.rows[0] || null;
  }

  async listarPaginado(
    query: QueryColaboradorDto,
  ): Promise<{ colaboradores: any[]; total: number }> {
    const page = Math.max(1, Number(query.page) || 1);
    const limit = Math.max(1, Math.min(100, Number(query.limit) || 20));
    const offset = (page - 1) * limit;

    let whereClausula = 'WHERE 1=1';
    const params: any[] = [];

    // Filtro por Empresa
    if (query.empresaId) {
      params.push(query.empresaId);
      whereClausula += ` AND empresa_id = $${params.length}`;
    }

    // Filtro por Filial
    if (query.filialId) {
      params.push(query.filialId);
      whereClausula += ` AND filial_id = $${params.length}`;
    }

    // Filtro por Situação (aceita 'ATIVO', 'INATIVO', 'ativo', 'inativo')
    if (query.situacao && query.situacao !== 'todas' && query.situacao !== 'todos') {
      const sit = query.situacao.trim();
      params.push(sit.toLowerCase());
      params.push(sit.toUpperCase());
      whereClausula += ` AND (LOWER(situacao) = $${params.length - 1} OR UPPER(situacao) = $${params.length})`;
    }

    // Filtro por Departamento / Setor
    const dept = query.departamentoId || query.setor;
    if (dept) {
      params.push(dept);
      whereClausula += ` AND (departamento_id = $${params.length} OR setor = $${params.length})`;
    }

    // Pesquisa textual (RF-02: Nome, CPF, Matrícula)
    const termo = query.search || query.q;
    if (termo && termo.trim()) {
      const tLimpo = `%${termo.trim()}%`;
      params.push(tLimpo);
      const p = `$${params.length}`;
      whereClausula += ` AND (
        LOWER(nome_completo) LIKE LOWER(${p}) OR
        LOWER(cpf) LIKE LOWER(${p}) OR
        LOWER(matricula) LIKE LOWER(${p})
      )`;
    }

    // Contagem total
    const countSql = `SELECT COUNT(*) as total FROM colaboradores ${whereClausula}`;
    const countRes = await this.db.query(countSql, params);
    const total = parseInt(countRes.rows[0]?.total || '0', 10);

    // Consulta de dados paginados
    params.push(limit);
    const paramLimit = `$${params.length}`;
    params.push(offset);
    const paramOffset = `$${params.length}`;

    const dataSql = `
      SELECT * FROM colaboradores
      ${whereClausula}
      ORDER BY id ASC
      LIMIT ${paramLimit} OFFSET ${paramOffset}
    `;

    const dataRes = await this.db.query(dataSql, params);
    return { colaboradores: dataRes.rows, total };
  }

  async inserir(dados: any, criadoPor: string, agora: string): Promise<any> {
    const res = await this.db.query(
      `INSERT INTO colaboradores (
        empresa_id, filial_id, matricula, nome_completo, cpf, data_nascimento,
        sexo, estado_civil, email, telefone, celular, cep, logradouro, numero,
        complemento, bairro, cidade, uf, departamento_id, cargo_id, data_admissao,
        cargo, setor, salario_base, situacao, observacoes, rg, criado_por, criado_em, atualizado_em
      ) VALUES (
        $1, $2, $3, $4, $5, $6,
        $7, $8, $9, $10, $11, $12, $13, $14,
        $15, $16, $17, $18, $19, $20, $21,
        $22, $23, $24, $25, $26, $27, $28, $29, $29
      ) RETURNING *`,
      [
        dados.empresa_id,
        dados.filial_id || null,
        dados.matricula,
        dados.nome_completo,
        dados.cpf,
        dados.data_nascimento,
        dados.sexo || null,
        dados.estado_civil || null,
        dados.email || null,
        dados.telefone || null,
        dados.celular || null,
        dados.cep || null,
        dados.logradouro || null,
        dados.numero || null,
        dados.complemento || null,
        dados.bairro || null,
        dados.cidade || null,
        dados.uf || null,
        dados.departamento_id || null,
        dados.cargo_id || null,
        dados.data_admissao || null,
        dados.cargo || dados.cargo_id || 'Não Informado',
        dados.setor || dados.departamento_id || 'Geral',
        dados.salario_base !== undefined ? dados.salario_base : 0,
        (dados.situacao || 'ativo').toLowerCase(),
        dados.observacoes || null,
        dados.rg || null,
        criadoPor,
        agora,
      ],
    );

    return res.rows[0];
  }

  async atualizar(id: number, camposParaAtualizar: Record<string, any>, agora: string): Promise<any> {
    const keys = Object.keys(camposParaAtualizar);
    if (keys.length === 0) {
      return this.buscarPorId(id);
    }

    const setClauses: string[] = [];
    const values: any[] = [];

    keys.forEach((key, index) => {
      setClauses.push(`${key} = $${index + 1}`);
      const val = key === 'situacao' && typeof camposParaAtualizar[key] === 'string'
        ? camposParaAtualizar[key].toLowerCase()
        : camposParaAtualizar[key];
      values.push(val);
    });

    values.push(agora);
    setClauses.push(`atualizado_em = $${values.length}`);

    values.push(id);
    const idParam = `$${values.length}`;

    const sql = `UPDATE colaboradores SET ${setClauses.join(', ')} WHERE id = ${idParam} RETURNING *`;
    const res = await this.db.query(sql, values);
    return res.rows[0];
  }

  async inativar(id: number, usuario: string, agora: string): Promise<any> {
    const res = await this.db.query(
      `UPDATE colaboradores SET situacao = 'inativo', atualizado_por = $1, atualizado_em = $2 WHERE id = $3 RETURNING *`,
      [usuario, agora, id],
    );
    return res.rows[0];
  }

  async inserirHistorico(
    colaboradorId: number,
    acao: string,
    campo: string,
    valorAnt: string | null,
    valorNovo: string | null,
    usuario: string,
    agora: string,
  ): Promise<void> {
    await this.db.query(
      `INSERT INTO historico_alteracoes (
        colaborador_id, data_hora, campo_alterado, valor_anterior, valor_novo, usuario_responsavel
      ) VALUES ($1, $2, $3, $4, $5, $6)`,
      [colaboradorId, agora, `${acao}:${campo}`, valorAnt, valorNovo, usuario],
    );
  }

  async inserirDependentes(colaboradorId: number, dependentes: any[]): Promise<void> {
    for (const d of dependentes) {
      if (d.nome && d.parentesco) {
        await this.db.query(
          `INSERT INTO dependentes (colaborador_id, nome, cpf, parentesco) VALUES ($1, $2, $3, $4)`,
          [colaboradorId, d.nome, d.cpf || '', d.parentesco],
        );
      }
    }
  }

  async buscarHistorico(colaboradorId: number): Promise<any[]> {
    const res = await this.db.query(
      `SELECT * FROM historico_alteracoes WHERE colaborador_id = $1 ORDER BY id DESC`,
      [colaboradorId],
    );
    return res.rows;
  }

  async obterMetricas(): Promise<any> {
    const resAtivos = await this.db.query(
      `SELECT COUNT(*) as total FROM colaboradores WHERE LOWER(situacao) = 'ativo'`,
    );
    const resInativos = await this.db.query(
      `SELECT COUNT(*) as total FROM colaboradores WHERE LOWER(situacao) = 'inativo'`,
    );
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
