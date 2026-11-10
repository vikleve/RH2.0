import {
  BadRequestException,
  ForbiddenException,
  Injectable,
  NotFoundException,
} from '@nestjs/common';
import { DatabaseService } from '../../database/database.service';
import {
  calcularHorasExtras,
  calcularAdicionalNoturno,
  calcularDescontoFaltas,
  calcularDescontoAtrasos,
  calcularDsrSobreVariaveis,
  calcularInssProgressivo,
  calcularIrrfProgressivo,
  calcularFgtsInformativo,
  arredondarMoeda,
  toDecimal,
} from './folha-calculos.engine';
import { Decimal } from 'decimal.js';

@Injectable()
export class FolhaService {
  constructor(private readonly db: DatabaseService) {}

  async listarFolhas(filtros: {
    competencia?: string;
    colaboradorId?: number;
    situacao?: string;
    setor?: string;
    termo?: string;
  }): Promise<any[]> {
    let sql = `
      SELECT f.*, c.nome_completo as colaborador_nome, c.matricula as colaborador_matricula, c.cargo as colaborador_cargo, c.setor as colaborador_setor
      FROM folhas_pagamento f
      JOIN colaboradores c ON c.id = f.colaborador_id
      WHERE 1=1
    `;
    const params: any[] = [];

    if (filtros.competencia) {
      params.push(filtros.competencia);
      sql += ` AND f.competencia = $${params.length}`;
    }
    if (filtros.colaboradorId) {
      params.push(filtros.colaboradorId);
      sql += ` AND f.colaborador_id = $${params.length}`;
    }
    if (filtros.situacao && filtros.situacao !== 'todas') {
      params.push(filtros.situacao);
      sql += ` AND f.situacao = $${params.length}`;
    }
    if (filtros.setor) {
      params.push(filtros.setor);
      sql += ` AND c.setor = $${params.length}`;
    }
    if (filtros.termo) {
      params.push(`%${filtros.termo}%`);
      const p = `$${params.length}`;
      sql += ` AND (LOWER(c.nome_completo) LIKE LOWER(${p}) OR LOWER(c.matricula) LIKE LOWER(${p}))`;
    }

    sql += ` ORDER BY f.id DESC`;
    const res = await this.db.query(sql, params);
    return res.rows;
  }

  async obterFolhaPorId(id: number): Promise<any> {
    const res = await this.db.query(
      `SELECT f.*, c.nome_completo as colaborador_nome, c.cpf as colaborador_cpf,
              c.matricula as colaborador_matricula, c.cargo as colaborador_cargo,
              c.setor as colaborador_setor, c.data_admissao as colaborador_admissao
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

    return folha;
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
    const numDependentes = parseInt(depRes.rows[0]?.total || 0, 10);

    const salarioContratual = toDecimal(dados.salario_base || colab.salario_base);
    const diasTrabalhados = toDecimal(dados.dias_trabalhados ?? 30);
    const diasMes = parseInt(dados.dias_mes ?? 30, 10);
    const horasDivisor = parseFloat(dados.horas_divisor ?? colab.horas_divisor ?? 220);

    // Salário base proporcional
    const salarioProporcional = arredondarMoeda(
      salarioContratual.dividedBy(diasMes).times(diasTrabalhados),
    );

    let totalProventos = new Decimal(salarioProporcional);
    let totalDescontos = new Decimal('0.00');
    const itensCalculados: any[] = [];

    // Item 1: Salário Base
    itensCalculados.push({
      codigo_rubrica: '001',
      descricao_rubrica: 'Salário Base (Proporcional)',
      tipo_rubrica: 'provento',
      referencia_valor: `${diasTrabalhados} dias`,
      valor_unitario: salarioContratual.toNumber(),
      valor_total: salarioProporcional.toNumber(),
      incide_inss: 1,
      incide_fgts: 1,
      incide_irrf: 1,
      memoria_calculo: `(${salarioContratual} / ${diasMes}) * ${diasTrabalhados}`,
    });

    // Processa eventos adicionais
    let totalVariaveis = new Decimal('0.00');
    if (Array.isArray(dados.eventos)) {
      for (const ev of dados.eventos) {
        if (ev.tipo === 'hora_extra') {
          const resHe = calcularHorasExtras(
            salarioContratual,
            horasDivisor,
            ev.quantidade,
            ev.percentual || 50,
          );
          totalProventos = totalProventos.plus(resHe.valor);
          totalVariaveis = totalVariaveis.plus(resHe.valor);
          itensCalculados.push({
            codigo_rubrica: '101',
            descricao_rubrica: `Horas Extras (${ev.percentual || 50}%)`,
            tipo_rubrica: 'provento',
            referencia_valor: `${ev.quantidade}h`,
            valor_total: resHe.valor.toNumber(),
            incide_inss: 1,
            incide_fgts: 1,
            incide_irrf: 1,
            memoria_calculo: resHe.memoria,
          });
        } else if (ev.tipo === 'adicional_noturno') {
          const resNot = calcularAdicionalNoturno(
            salarioContratual,
            horasDivisor,
            ev.quantidade,
            ev.percentual || 20,
            ev.reducao_ficta || false,
          );
          totalProventos = totalProventos.plus(resNot.valor);
          totalVariaveis = totalVariaveis.plus(resNot.valor);
          itensCalculados.push({
            codigo_rubrica: '102',
            descricao_rubrica: 'Adicional Noturno',
            tipo_rubrica: 'provento',
            referencia_valor: `${ev.quantidade}h`,
            valor_total: resNot.valor.toNumber(),
            incide_inss: 1,
            incide_fgts: 1,
            incide_irrf: 1,
            memoria_calculo: resNot.memoria,
          });
        } else if (ev.tipo === 'falta') {
          const resFalta = calcularDescontoFaltas(salarioContratual, ev.quantidade, diasMes);
          totalDescontos = totalDescontos.plus(resFalta.valor);
          itensCalculados.push({
            codigo_rubrica: '201',
            descricao_rubrica: 'Faltas Integrais',
            tipo_rubrica: 'desconto',
            referencia_valor: `${ev.quantidade}d`,
            valor_total: resFalta.valor.toNumber(),
            incide_inss: 0,
            incide_fgts: 0,
            incide_irrf: 0,
            memoria_calculo: resFalta.memoria,
          });
        } else if (ev.tipo === 'atraso') {
          const resAtraso = calcularDescontoAtrasos(salarioContratual, horasDivisor, ev.quantidade);
          totalDescontos = totalDescontos.plus(resAtraso.valor);
          itensCalculados.push({
            codigo_rubrica: '202',
            descricao_rubrica: 'Horas de Atraso',
            tipo_rubrica: 'desconto',
            referencia_valor: `${ev.quantidade}h`,
            valor_total: resAtraso.valor.toNumber(),
            incide_inss: 0,
            incide_fgts: 0,
            incide_irrf: 0,
            memoria_calculo: resAtraso.memoria,
          });
        }
      }
    }

    // DSR sobre variáveis se houver horas extras ou adicional noturno
    if (totalVariaveis.greaterThan(0)) {
      const resDsr = calcularDsrSobreVariaveis(totalVariaveis);
      totalProventos = totalProventos.plus(resDsr.valor);
      itensCalculados.push({
        codigo_rubrica: '103',
        descricao_rubrica: 'DSR sobre Horas Extras / Noturno',
        tipo_rubrica: 'provento',
        referencia_valor: 'DSR',
        valor_total: resDsr.valor.toNumber(),
        incide_inss: 1,
        incide_fgts: 1,
        incide_irrf: 1,
        memoria_calculo: resDsr.memoria,
      });
    }

    // Base legal para encargos
    const baseInss = totalProventos;
    const baseFgts = totalProventos;

    // Cálculo INSS Progressivo
    const resInss = calcularInssProgressivo(baseInss);
    totalDescontos = totalDescontos.plus(resInss.valor);
    itensCalculados.push({
      codigo_rubrica: '501',
      descricao_rubrica: 'INSS (Faixas Progressivas)',
      tipo_rubrica: 'desconto',
      referencia_valor: 'INSS',
      valor_total: resInss.valor.toNumber(),
      incide_inss: 0,
      incide_fgts: 0,
      incide_irrf: 0,
      memoria_calculo: resInss.memoria,
    });

    // Cálculo IRRF
    const resIrrf = calcularIrrfProgressivo(baseInss, resInss.valor, numDependentes);
    if (resIrrf.valor.greaterThan(0)) {
      totalDescontos = totalDescontos.plus(resIrrf.valor);
      itensCalculados.push({
        codigo_rubrica: '502',
        descricao_rubrica: 'IRRF (Retenção na Fonte)',
        tipo_rubrica: 'desconto',
        referencia_valor: 'IRRF',
        valor_total: resIrrf.valor.toNumber(),
        incide_inss: 0,
        incide_fgts: 0,
        incide_irrf: 0,
        memoria_calculo: resIrrf.memoria,
      });
    }

    // FGTS Informativo
    const fgtsInformativo = calcularFgtsInformativo(baseFgts);

    // Salário Líquido
    const salarioLiquido = arredondarMoeda(totalProventos.minus(totalDescontos));

    const agora = new Date().toISOString().replace('T', ' ').slice(0, 19);

    // Verifica se já existe folha para o colaborador e competência
    const folhaExistente = await this.db.query(
      `SELECT * FROM folhas_pagamento WHERE colaborador_id = $1 AND competencia = $2`,
      [dados.colaborador_id, dados.competencia],
    );

    let folhaId: number;

    if (folhaExistente.rows.length > 0) {
      const f = folhaExistente.rows[0];
      if (f.situacao === 'fechada') {
        throw new ForbiddenException({
          sucesso: false,
          mensagem: `A folha #${f.id} está fechada e não permite recálculos sem reabertura formal.`,
        });
      }
      folhaId = f.id;

      await this.db.query(
        `UPDATE folhas_pagamento SET
          total_proventos = $1, total_descontos = $2, salario_liquido = $3,
          base_inss = $4, base_fgts = $5, valor_fgts_informativo = $6,
          base_irrf = $7, situacao = 'calculada', atualizado_por = $8, atualizado_em = $9
         WHERE id = $10`,
        [
          totalProventos.toNumber(),
          totalDescontos.toNumber(),
          salarioLiquido.toNumber(),
          baseInss.toNumber(),
          baseFgts.toNumber(),
          fgtsInformativo.toNumber(),
          baseInss.toNumber(),
          usuario,
          agora,
          folhaId,
        ],
      );

      // Limpa itens antigos para reinserção atualizada
      await this.db.query(`DELETE FROM folha_itens WHERE folha_id = $1`, [folhaId]);
    } else {
      const insRes = await this.db.query(
        `INSERT INTO folhas_pagamento (
          colaborador_id, competencia, periodo_inicio, periodo_fim, data_pagamento,
          dias_trabalhados, dias_mes, horas_mensais_divisor, salario_base_contratual,
          salario_base_proporcional, total_proventos, total_descontos, salario_liquido,
          base_inss, base_fgts, valor_fgts_informativo, base_irrf, situacao,
          criado_por, criado_em, atualizado_por, atualizado_em
        ) VALUES (
          $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17,
          'calculada', $18, $19, $18, $19
        ) RETURNING id`,
        [
          dados.colaborador_id,
          dados.competencia,
          dados.periodo_inicio || `${dados.competencia}-01`,
          dados.periodo_fim || `${dados.competencia}-30`,
          dados.data_pagamento || null,
          diasTrabalhados.toNumber(),
          diasMes,
          horasDivisor,
          salarioContratual.toNumber(),
          salarioProporcional.toNumber(),
          totalProventos.toNumber(),
          totalDescontos.toNumber(),
          salarioLiquido.toNumber(),
          baseInss.toNumber(),
          baseFgts.toNumber(),
          fgtsInformativo.toNumber(),
          baseInss.toNumber(),
          usuario,
          agora,
        ],
      );
      folhaId = insRes.rows[0].id;

      await this.db.query(
        `INSERT INTO folha_historico (folha_id, data_hora, acao, descricao, usuario_responsavel)
         VALUES ($1, $2, 'CRIACAO', 'Folha criada e calculada pelo sistema', $3)`,
        [folhaId, agora, usuario],
      );
    }

    // Insere itens calculados
    for (const item of itensCalculados) {
      await this.db.query(
        `INSERT INTO folha_itens (
          folha_id, codigo_evento, descricao, tipo, referencia,
          unidade_referencia, valor_total, origem, memoria_calculo, criado_em
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)`,
        [
          folhaId,
          item.codigo_rubrica,
          item.descricao_rubrica,
          item.tipo_rubrica,
          typeof item.referencia_valor === 'number' ? item.referencia_valor : 0,
          String(item.referencia_valor || ''),
          item.valor_total,
          'calculado',
          item.memoria_calculo,
          agora,
        ],
      );
    }

    return this.obterFolhaPorId(folhaId);
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

