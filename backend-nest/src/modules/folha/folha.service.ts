import {
  BadRequestException,
  ForbiddenException,
  Injectable,
  NotFoundException,
} from '@nestjs/common';
import { DatabaseService } from '../../database/database.service';
import {
  processarCalculoCompletoFolha,
  ResultadoCalculoFolha,
} from './folha-calculos.engine';

@Injectable()
export class FolhaService {
  constructor(private readonly db: DatabaseService) {}

  private normalizarValoresFolha(folha: any): any {
    if (!folha) return folha;
    return {
      ...folha,
      dias_trabalhados: Number(folha.dias_trabalhados || 0),
      dias_mes: Number(folha.dias_mes || 30),
      horas_mensais_divisor: Number(folha.horas_mensais_divisor || 220),
      salario_base_contratual: Number(folha.salario_base_contratual || 0),
      salario_base_proporcional: Number(folha.salario_base_proporcional || 0),
      total_proventos: Number(folha.total_proventos || 0),
      total_descontos: Number(folha.total_descontos || 0),
      salario_liquido: Number(folha.salario_liquido || 0),
      base_inss: Number(folha.base_inss || 0),
      base_fgts: Number(folha.base_fgts || 0),
      valor_fgts_informativo: Number(folha.valor_fgts_informativo || 0),
      base_irrf: Number(folha.base_irrf || 0),
      itens: (folha.itens || []).map((it: any) => ({
        ...it,
        referencia: Number(it.referencia || 0),
        valor_unitario: Number(it.valor_unitario || 0),
        valor_total: Number(it.valor_total || 0),
      })),
    };
  }

  async simularFolha(dados: any): Promise<ResultadoCalculoFolha> {
    if (!dados.colaborador_id) {
      throw new BadRequestException({
        sucesso: false,
        mensagem: 'O colaborador é obrigatório para a simulação da folha.',
      });
    }

    const colabRes = await this.db.query(
      `SELECT * FROM colaboradores WHERE id = $1`,
      [dados.colaborador_id],
    );
    if (colabRes.rows.length === 0) {
      throw new NotFoundException({
        sucesso: false,
        mensagem: 'Colaborador não encontrado para simulação.',
      });
    }
    const colab = colabRes.rows[0];

    const depRes = await this.db.query(
      `SELECT COUNT(*) as total FROM dependentes WHERE colaborador_id = $1`,
      [dados.colaborador_id],
    );
    const numDependentes = parseInt(depRes.rows[0]?.total || '0', 10);

    const resultado = processarCalculoCompletoFolha({
      salario_base: dados.salario_base || colab.salario_base,
      dias_trabalhados: dados.dias_trabalhados ?? 30,
      dias_mes: dados.dias_mes ? parseInt(dados.dias_mes, 10) : 30,
      horas_divisor: dados.horas_divisor ? parseFloat(dados.horas_divisor) : (colab.horas_divisor || 220),
      numero_dependentes: numDependentes,
      eventos: dados.eventos || [],
    });

    return resultado;
  }

  async listarFolhas(filtros: {
    competencia?: string;
    colaboradorId?: number;
    situacao?: string;
    setor?: string;
    termo?: string;
  } = {}): Promise<any[]> {
    let sql = `
      SELECT f.*, c.nome_completo as colaborador_nome, c.cpf as colaborador_cpf,
             c.matricula as colaborador_matricula, c.cargo as colaborador_cargo,
             c.setor as colaborador_setor
      FROM folhas_pagamento f
      JOIN colaboradores c ON c.id = f.colaborador_id
      WHERE 1=1
    `;
    const params: any[] = [];
    let idx = 1;

    if (filtros.competencia) {
      sql += ` AND f.competencia = $${idx++}`;
      params.push(filtros.competencia);
    }
    if (filtros.colaboradorId) {
      sql += ` AND f.colaborador_id = $${idx++}`;
      params.push(filtros.colaboradorId);
    }
    if (filtros.situacao && filtros.situacao !== 'todos') {
      sql += ` AND f.situacao = $${idx++}`;
      params.push(filtros.situacao);
    }
    if (filtros.setor) {
      sql += ` AND c.setor = $${idx++}`;
      params.push(filtros.setor);
    }
    if (filtros.termo) {
      sql += ` AND (c.nome_completo ILIKE $${idx} OR c.cpf ILIKE $${idx} OR c.matricula ILIKE $${idx})`;
      params.push(`%${filtros.termo}%`);
      idx++;
    }

    sql += ` ORDER BY f.competencia DESC, c.nome_completo ASC`;
    const res = await this.db.query(sql, params);
    return res.rows.map((r) => this.normalizarValoresFolha(r));
  }

  async obterFolhaPorId(id: number): Promise<any> {
    const res = await this.db.query(
      `SELECT f.*, c.nome_completo as colaborador_nome, c.cpf as colaborador_cpf,
              c.matricula as colaborador_matricula, c.cargo as colaborador_cargo,
              c.setor as colaborador_setor, c.data_admissao as colaborador_data_admissao
       FROM folhas_pagamento f
       JOIN colaboradores c ON c.id = f.colaborador_id
       WHERE f.id = $1`,
      [id],
    );

    if (res.rows.length === 0) {
      throw new NotFoundException({
        sucesso: false,
        mensagem: `Folha de pagamento #${id} não encontrada.`,
      });
    }

    const folha = res.rows[0];
    const itensRes = await this.db.query(
      `SELECT * FROM folha_itens WHERE folha_id = $1 ORDER BY id ASC`,
      [id],
    );
    folha.itens = itensRes.rows;

    const histRes = await this.db.query(
      `SELECT * FROM folha_historico WHERE folha_id = $1 ORDER BY id DESC`,
      [id],
    );
    folha.historico = histRes.rows;

    return this.normalizarValoresFolha(folha);
  }

  async criarOuAtualizarFolha(dados: any, usuario = 'Sistema/Administrador'): Promise<any> {
    const colabRes = await this.db.query(
      `SELECT * FROM colaboradores WHERE id = $1`,
      [dados.colaborador_id],
    );
    if (colabRes.rows.length === 0) {
      throw new NotFoundException({ sucesso: false, mensagem: 'Colaborador não encontrado.' });
    }
    const colab = colabRes.rows[0];

    const depRes = await this.db.query(
      `SELECT COUNT(*) as total FROM dependentes WHERE colaborador_id = $1`,
      [dados.colaborador_id],
    );
    const numDependentes = parseInt(depRes.rows[0]?.total || '0', 10);

    const calc = processarCalculoCompletoFolha({
      salario_base: dados.salario_base || colab.salario_base,
      dias_trabalhados: dados.dias_trabalhados ?? 30,
      dias_mes: dados.dias_mes ? parseInt(dados.dias_mes, 10) : 30,
      horas_divisor: dados.horas_divisor ? parseFloat(dados.horas_divisor) : (colab.horas_divisor || 220),
      numero_dependentes: numDependentes,
      eventos: dados.eventos || [],
    });

    const agora = new Date().toISOString().replace('T', ' ').slice(0, 19);

    // Verifica unicidade de folha para o mesmo colaborador na mesma competência
    const folhaExistente = await this.db.query(
      `SELECT * FROM folhas_pagamento WHERE colaborador_id = $1 AND competencia = $2`,
      [dados.colaborador_id, dados.competencia],
    );

    let folhaId: number;
    const client = await this.db.getClient();

    try {
      await client.query('BEGIN');

      if (folhaExistente.rows.length > 0) {
        const f = folhaExistente.rows[0];
        if (f.situacao === 'fechada') {
          throw new ForbiddenException({
            sucesso: false,
            mensagem: `A folha #${f.id} está fechada e não permite edições sem reabertura formal.`,
          });
        }
        folhaId = f.id;

        await client.query(
          `UPDATE folhas_pagamento SET
            dias_trabalhados = $1, dias_mes = $2, horas_mensais_divisor = $3,
            salario_base_contratual = $4, salario_base_proporcional = $5,
            total_proventos = $6, total_descontos = $7, salario_liquido = $8,
            base_inss = $9, base_fgts = $10, valor_fgts_informativo = $11,
            base_irrf = $12, situacao = 'calculada', observacoes = $13,
            atualizado_por = $14, atualizado_em = $15
           WHERE id = $16`,
          [
            calc.dias_trabalhados,
            calc.dias_mes,
            calc.horas_mensais_divisor,
            calc.salario_base_contratual,
            calc.salario_base_proporcional,
            calc.total_proventos,
            calc.total_descontos,
            calc.salario_liquido,
            calc.base_inss,
            calc.base_fgts,
            calc.valor_fgts_informativo,
            calc.base_irrf,
            dados.observacoes || f.observacoes || '',
            usuario,
            agora,
            folhaId,
          ],
        );

        // Limpa itens antigos para reinserção atômica
        await client.query(`DELETE FROM folha_itens WHERE folha_id = $1`, [folhaId]);

        await client.query(
          `INSERT INTO folha_historico (folha_id, data_hora, acao, descricao, usuario_responsavel)
           VALUES ($1, $2, 'ATUALIZACAO', 'Folha recalculada e atualizada com sucesso', $3)`,
          [folhaId, agora, usuario],
        );
      } else {
        const insRes = await client.query(
          `INSERT INTO folhas_pagamento (
            colaborador_id, competencia, periodo_inicio, periodo_fim, data_pagamento,
            dias_trabalhados, dias_mes, horas_mensais_divisor, salario_base_contratual,
            salario_base_proporcional, total_proventos, total_descontos, salario_liquido,
            base_inss, base_fgts, valor_fgts_informativo, base_irrf, situacao,
            observacoes, criado_por, criado_em, atualizado_por, atualizado_em
          ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17,
            'calculada', $18, $19, $20, $19, $20
          ) RETURNING id`,
          [
            dados.colaborador_id,
            dados.competencia,
            dados.periodo_inicio || `${dados.competencia}-01`,
            dados.periodo_fim || `${dados.competencia}-30`,
            dados.data_pagamento || null,
            calc.dias_trabalhados,
            calc.dias_mes,
            calc.horas_mensais_divisor,
            calc.salario_base_contratual,
            calc.salario_base_proporcional,
            calc.total_proventos,
            calc.total_descontos,
            calc.salario_liquido,
            calc.base_inss,
            calc.base_fgts,
            calc.valor_fgts_informativo,
            calc.base_irrf,
            dados.observacoes || null,
            usuario,
            agora,
          ],
        );
        folhaId = insRes.rows[0].id;

        await client.query(
          `INSERT INTO folha_historico (folha_id, data_hora, acao, descricao, usuario_responsavel)
           VALUES ($1, $2, 'CRIACAO', 'Folha criada e calculada pelo motor oficial', $3)`,
          [folhaId, agora, usuario],
        );
      }

      // Insere os itens oficiais calculados pelo motor
      for (const item of calc.itens) {
        await client.query(
          `INSERT INTO folha_itens (
            folha_id, codigo_evento, descricao, tipo, referencia,
            unidade_referencia, valor_unitario, valor_total, origem, memoria_calculo, criado_em
          ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)`,
          [
            folhaId,
            item.codigo_evento,
            item.descricao,
            item.tipo,
            item.referencia,
            item.unidade_referencia,
            item.valor_unitario,
            item.valor_total,
            item.origem,
            item.memoria_calculo,
            agora,
          ],
        );
      }

      await client.query('COMMIT');
    } catch (e) {
      await client.query('ROLLBACK');
      throw e;
    } finally {
      client.release();
    }

    return this.obterFolhaPorId(folhaId);
  }

  async recalcularFolha(id: number, dados: any = {}, usuario = 'Sistema/Administrador'): Promise<any> {
    const folhaExistente = await this.obterFolhaPorId(id);
    if (folhaExistente.situacao === 'fechada') {
      throw new ForbiddenException({
        sucesso: false,
        mensagem: `A folha #${id} está fechada e não permite recálculo sem procedimento formal de reabertura.`,
      });
    }

    const payload = {
      ...dados,
      colaborador_id: folhaExistente.colaborador_id,
      competencia: folhaExistente.competencia,
      periodo_inicio: dados.periodo_inicio || folhaExistente.periodo_inicio,
      periodo_fim: dados.periodo_fim || folhaExistente.periodo_fim,
      data_pagamento: dados.data_pagamento || folhaExistente.data_pagamento,
      dias_trabalhados: dados.dias_trabalhados ?? folhaExistente.dias_trabalhados,
      dias_mes: dados.dias_mes ?? folhaExistente.dias_mes,
      horas_divisor: dados.horas_divisor ?? folhaExistente.horas_mensais_divisor,
      eventos: dados.eventos || [],
      observacoes: dados.observacoes || folhaExistente.observacoes,
    };

    const atualizada = await this.criarOuAtualizarFolha(payload, usuario);

    const agora = new Date().toISOString().replace('T', ' ').slice(0, 19);
    await this.db.query(
      `INSERT INTO folha_historico (folha_id, data_hora, acao, descricao, usuario_responsavel)
       VALUES ($1, $2, 'RECALCULO', 'Recálculo oficial executado e persistido com sucesso', $3)`,
      [id, agora, usuario],
    );

    return atualizada;
  }

  async fecharFolha(id: number, usuario = 'Sistema/Administrador'): Promise<any> {
    const folha = await this.obterFolhaPorId(id);
    if (folha.situacao === 'fechada') {
      throw new BadRequestException({ sucesso: false, mensagem: 'Esta folha já está fechada.' });
    }
    const agora = new Date().toISOString().replace('T', ' ').slice(0, 19);
    await this.db.query(
      `UPDATE folhas_pagamento SET situacao = 'fechada', fechado_por = $1, fechado_em = $2 WHERE id = $3`,
      [usuario, agora, id],
    );
    await this.db.query(
      `INSERT INTO folha_historico (folha_id, data_hora, acao, descricao, usuario_responsavel)
       VALUES ($1, $2, 'FECHAMENTO', 'Fechamento formal contábil da folha', $3)`,
      [id, agora, usuario],
    );
    return this.obterFolhaPorId(id);
  }

  async reabrirFolha(id: number, motivo: string, usuario = 'Sistema/Administrador'): Promise<any> {
    const folha = await this.obterFolhaPorId(id);
    if (!motivo || !motivo.trim()) {
      throw new BadRequestException({ sucesso: false, mensagem: 'Justificativa para reabertura é obrigatória.' });
    }
    const agora = new Date().toISOString().replace('T', ' ').slice(0, 19);
    await this.db.query(
      `UPDATE folhas_pagamento SET situacao = 'calculada', atualizado_por = $1, atualizado_em = $2 WHERE id = $3`,
      [usuario, agora, id],
    );
    await this.db.query(
      `INSERT INTO folha_historico (folha_id, data_hora, acao, descricao, usuario_responsavel)
       VALUES ($1, $2, 'REABERTURA', $3, $4)`,
      [id, agora, `Reaberta para edição. Justificativa: ${motivo}`, usuario],
    );
    return this.obterFolhaPorId(id);
  }

  async cancelarFolha(id: number, usuario = 'Sistema/Administrador'): Promise<any> {
    await this.obterFolhaPorId(id);
    const agora = new Date().toISOString().replace('T', ' ').slice(0, 19);
    await this.db.query(
      `UPDATE folhas_pagamento SET situacao = 'cancelada', atualizado_por = $1, atualizado_em = $2 WHERE id = $3`,
      [usuario, agora, id],
    );
    await this.db.query(
      `INSERT INTO folha_historico (folha_id, data_hora, acao, descricao, usuario_responsavel)
       VALUES ($1, $2, 'CANCELAMENTO', 'Folha cancelada formalmente', $3)`,
      [id, agora, usuario],
    );
    return this.obterFolhaPorId(id);
  }
}
