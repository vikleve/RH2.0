import { Decimal } from 'decimal.js';
import { CATALOGO_EVENTOS_FOLHA, EventoFolhaCatalogo } from './catalogo-eventos';

// Configura precisão e modo de arredondamento ROUND_HALF_UP (padrão financeiro)
Decimal.set({ precision: 20, rounding: Decimal.ROUND_HALF_UP });

export function toDecimal(val: any): Decimal {
  if (val === null || val === undefined || val === '') {
    return new Decimal('0.00');
  }
  if (val instanceof Decimal) {
    return val;
  }
  try {
    let strVal = String(val).replace('R$', '').trim();
    if (strVal.includes(',') && !strVal.includes('.')) {
      strVal = strVal.replace(',', '.');
    } else if (strVal.includes(',') && strVal.includes('.')) {
      strVal = strVal.replace(/\./g, '').replace(',', '.');
    }
    return new Decimal(strVal);
  } catch {
    return new Decimal('0.00');
  }
}

export function arredondarMoeda(val: any): Decimal {
  return toDecimal(val).toDecimalPlaces(2, Decimal.ROUND_HALF_UP);
}

// ---------------------------------------------------------------------------
// TABELAS PROGRESSIVAS VIGENTES (HOMOLOGADAS EM PORTARIA OFICIAL 2026)
// ---------------------------------------------------------------------------
export const TABELA_INSS_PADRAO_2026 = [
  { min: new Decimal('0.00'), max: new Decimal('1518.00'), aliq: new Decimal('7.5') },
  { min: new Decimal('1518.00'), max: new Decimal('2793.88'), aliq: new Decimal('9.0') },
  { min: new Decimal('2793.88'), max: new Decimal('4190.83'), aliq: new Decimal('12.0') },
  { min: new Decimal('4190.83'), max: new Decimal('8157.41'), aliq: new Decimal('14.0') },
];
export const TETO_INSS_PADRAO_2026 = new Decimal('8157.41');

export const TABELA_IRRF_PADRAO_2026 = [
  { min: new Decimal('0.00'), max: new Decimal('2259.20'), aliq: new Decimal('0.0'), ded: new Decimal('0.00') },
  { min: new Decimal('2259.20'), max: new Decimal('2826.65'), aliq: new Decimal('7.5'), ded: new Decimal('169.44') },
  { min: new Decimal('2826.65'), max: new Decimal('3751.05'), aliq: new Decimal('15.0'), ded: new Decimal('381.44') },
  { min: new Decimal('3751.05'), max: new Decimal('4664.68'), aliq: new Decimal('22.5'), ded: new Decimal('662.77') },
  { min: new Decimal('4664.68'), max: null, aliq: new Decimal('27.5'), ded: new Decimal('896.00') },
];
export const DEDUCAO_DEPENDENTE_IRRF_PADRAO = new Decimal('189.59');
export const ALIQUOTA_FGTS_PADRAO = new Decimal('8.0');

export function calcularValorHora(salarioBase: any, horasDivisor = 220): Decimal {
  const sb = toDecimal(salarioBase);
  const hd = toDecimal(horasDivisor);
  if (hd.isZero()) return new Decimal('0.00');
  return sb.dividedBy(hd);
}

export function calcularHorasExtras(
  salarioBase: any,
  horasDivisor = 220,
  qtdHoras: any = 0,
  percentualAdicional: any = 50,
): { valor: Decimal; memoria: string } {
  const vHora = calcularValorHora(salarioBase, horasDivisor);
  const qtd = toDecimal(qtdHoras);
  const perc = toDecimal(percentualAdicional);
  const fator = new Decimal('1.00').plus(perc.dividedBy(100));
  const total = arredondarMoeda(vHora.times(qtd).times(fator));
  const memoria = `${qtd}h extras (${perc}%) sobre hora normal R$ ${arredondarMoeda(vHora)} = R$ ${total}`;
  return { valor: total, memoria };
}

export function calcularAdicionalNoturno(
  salarioBase: any,
  horasDivisor = 220,
  horasNoturnas: any = 0,
  percentualNoturno: any = 20,
  aplicarReducaoFicta = false,
  fatorReducao = 1.142857,
): { valor: Decimal; memoria: string } {
  const vHora = calcularValorHora(salarioBase, horasDivisor);
  let qtd = toDecimal(horasNoturnas);
  if (aplicarReducaoFicta) {
    qtd = qtd.times(toDecimal(fatorReducao));
  }
  const perc = toDecimal(percentualNoturno).dividedBy(100);
  const total = arredondarMoeda(vHora.times(qtd).times(perc));
  const memoria = `${qtd}h noturnas (${percentualNoturno}%) sobre hora normal R$ ${arredondarMoeda(vHora)} = R$ ${total}`;
  return { valor: total, memoria };
}

export function calcularDescontoFaltas(
  salarioBase: any,
  diasFalta: any = 0,
  diasMes = 30,
): { valor: Decimal; memoria: string } {
  const sb = toDecimal(salarioBase);
  const qtd = toDecimal(diasFalta);
  const dm = toDecimal(diasMes);
  if (dm.isZero()) return { valor: new Decimal('0.00'), memoria: '' };
  const vDia = sb.dividedBy(dm);
  const total = arredondarMoeda(vDia.times(qtd));
  const memoria = `${qtd} dia(s) de falta sobre valor diário R$ ${arredondarMoeda(vDia)} = R$ ${total}`;
  return { valor: total, memoria };
}

export function calcularDescontoAtrasos(
  salarioBase: any,
  horasDivisor = 220,
  horasAtraso: any = 0,
): { valor: Decimal; memoria: string } {
  const vHora = calcularValorHora(salarioBase, horasDivisor);
  const qtd = toDecimal(horasAtraso);
  const total = arredondarMoeda(vHora.times(qtd));
  const memoria = `${qtd}h de atraso sobre hora normal R$ ${arredondarMoeda(vHora)} = R$ ${total}`;
  return { valor: total, memoria };
}

export function calcularDsrSobreVariaveis(
  valorVariaveis: any,
  diasUteis = 25,
  domingosEFeriados = 5,
): { valor: Decimal; memoria: string } {
  const vv = toDecimal(valorVariaveis);
  const du = toDecimal(diasUteis);
  const df = toDecimal(domingosEFeriados);
  if (du.isZero()) return { valor: new Decimal('0.00'), memoria: '' };
  const total = arredondarMoeda(vv.dividedBy(du).times(df));
  const memoria = `DSR: (R$ ${arredondarMoeda(vv)} / ${du} dias úteis) * ${df} repousos = R$ ${total}`;
  return { valor: total, memoria };
}

export function calcularInssProgressivo(
  baseCalculo: any,
  teto = TETO_INSS_PADRAO_2026,
): { valor: Decimal; memoria: string; detalhesFaixas: any[] } {
  let base = toDecimal(baseCalculo);
  if (base.greaterThan(teto)) {
    base = teto;
  }
  let totalInss = new Decimal('0.00');
  const partes: string[] = [];
  const detalhesFaixas: any[] = [];

  for (let i = 0; i < TABELA_INSS_PADRAO_2026.length; i++) {
    const faixa = TABELA_INSS_PADRAO_2026[i];
    if (base.lessThanOrEqualTo(faixa.min)) continue;

    const limiteSuperior = faixa.max && base.greaterThan(faixa.max) ? faixa.max : base;
    const baseFaixa = limiteSuperior.minus(faixa.min);
    if (baseFaixa.greaterThan(0)) {
      const valorFaixa = baseFaixa.times(faixa.aliq).dividedBy(100);
      totalInss = totalInss.plus(valorFaixa);
      detalhesFaixas.push({
        faixa: i + 1,
        aliquota: faixa.aliq.toNumber(),
        base: baseFaixa.toNumber(),
        valor: arredondarMoeda(valorFaixa).toNumber(),
      });
      partes.push(`Faixa ${faixa.aliq}%: R$ ${arredondarMoeda(valorFaixa)}`);
    }
  }

  const finalInss = arredondarMoeda(totalInss);
  const memoria = `INSS Progressivo sobre R$ ${arredondarMoeda(base)}: ${partes.join(' + ')} = R$ ${finalInss}`;
  return { valor: finalInss, memoria, detalhesFaixas };
}

export function calcularIrrfProgressivo(
  baseCalculoBruta: any,
  inssDescontado: any = 0,
  dependentes = 0,
  deducaoPorDependente = DEDUCAO_DEPENDENTE_IRRF_PADRAO,
): { valor: Decimal; memoria: string; baseLiquida: Decimal } {
  const bruta = toDecimal(baseCalculoBruta);
  const inss = toDecimal(inssDescontado);
  const dedDep = toDecimal(dependentes).times(toDecimal(deducaoPorDependente));
  const baseLiquida = bruta.minus(inss).minus(dedDep);

  if (baseLiquida.lessThanOrEqualTo(0)) {
    return {
      valor: new Decimal('0.00'),
      memoria: 'Base líquida de IRRF isenta ou menor/igual a zero.',
      baseLiquida: new Decimal('0.00'),
    };
  }

  let faixaAplicada: any = null;
  for (const f of TABELA_IRRF_PADRAO_2026) {
    if (f.max === null || baseLiquida.lessThanOrEqualTo(f.max)) {
      faixaAplicada = f;
      break;
    }
  }

  if (!faixaAplicada || faixaAplicada.aliq.isZero()) {
    return {
      valor: new Decimal('0.00'),
      memoria: `Isento de IRRF (Base líquida: R$ ${arredondarMoeda(baseLiquida)})`,
      baseLiquida: arredondarMoeda(baseLiquida),
    };
  }

  const impostoBruto = baseLiquida.times(faixaAplicada.aliq).dividedBy(100);
  const impostoLiquido = impostoBruto.minus(faixaAplicada.ded);
  const valorFinal = arredondarMoeda(Decimal.max(impostoLiquido, new Decimal('0.00')));
  const memoria = `IRRF (${faixaAplicada.aliq}% sobre base líquida R$ ${arredondarMoeda(baseLiquida)}) - parcela deduzir R$ ${faixaAplicada.ded} = R$ ${valorFinal}`;
  return { valor: valorFinal, memoria, baseLiquida: arredondarMoeda(baseLiquida) };
}

export function calcularFgtsInformativo(baseCalculo: any, aliquota = ALIQUOTA_FGTS_PADRAO): Decimal {
  const base = toDecimal(baseCalculo);
  return arredondarMoeda(base.times(aliquota).dividedBy(100));
}

// ---------------------------------------------------------------------------
// MOTOR COMPLETO DE CÁLCULO E SIMULAÇÃO DE FOLHA DE PAGAMENTO
// ---------------------------------------------------------------------------
export interface ItemFolhaCalculado {
  codigo_evento: string;
  descricao: string;
  tipo: 'provento' | 'desconto' | 'informativo';
  referencia: number;
  unidade_referencia: string;
  valor_unitario: number;
  valor_total: number;
  origem: 'sistema' | 'calculado' | 'manual' | 'importado';
  incide_inss: number;
  incide_irrf: number;
  incide_fgts: number;
  memoria_calculo: string;
  situacao_validacao?: string;
}

export interface ResultadoCalculoFolha {
  salario_base_contratual: number;
  salario_base_proporcional: number;
  dias_trabalhados: number;
  dias_mes: number;
  horas_mensais_divisor: number;
  total_proventos: number;
  total_descontos: number;
  salario_liquido: number;
  base_inss: number;
  base_irrf: number;
  base_fgts: number;
  valor_fgts_informativo: number;
  itens: ItemFolhaCalculado[];
}

export function processarCalculoCompletoFolha(params: {
  salario_base: number | string | Decimal;
  dias_trabalhados?: number | string | Decimal;
  dias_mes?: number;
  horas_divisor?: number;
  numero_dependentes?: number;
  eventos?: any[];
}): ResultadoCalculoFolha {
  const salarioContratual = arredondarMoeda(params.salario_base);
  const diasMes = params.dias_mes && params.dias_mes > 0 ? params.dias_mes : 30;
  const diasTrabalhados = toDecimal(params.dias_trabalhados ?? diasMes);
  const horasDivisor = params.horas_divisor && params.horas_divisor > 0 ? params.horas_divisor : 220;
  const numDependentes = params.numero_dependentes || 0;

  // 1. Salário base proporcional
  const salarioProporcional = arredondarMoeda(
    salarioContratual.dividedBy(diasMes).times(Decimal.min(diasTrabalhados, diasMes)),
  );

  let totalProventos = new Decimal(salarioProporcional);
  let totalDescontos = new Decimal('0.00');
  let totalVariaveis = new Decimal('0.00');
  const itensCalculados: ItemFolhaCalculado[] = [];

  // Item base oficial: Salário Mensal (0001)
  itensCalculados.push({
    codigo_evento: '0001',
    descricao: 'Salário Base (Proporcional)',
    tipo: 'provento',
    referencia: diasTrabalhados.toNumber(),
    unidade_referencia: 'dias',
    valor_unitario: salarioContratual.toNumber(),
    valor_total: salarioProporcional.toNumber(),
    origem: 'sistema',
    incide_inss: 1,
    incide_irrf: 1,
    incide_fgts: 1,
    memoria_calculo: `(R$ ${salarioContratual} / ${diasMes}d) * ${diasTrabalhados} dias trabalhados`,
    situacao_validacao: 'HOMOLOGADO',
  });

  // 2. Processar eventos informados
  const eventosInformados = Array.isArray(params.eventos) ? params.eventos : [];

  for (const ev of eventosInformados) {
    const cod = String(ev.codigo || '').trim();
    const evCat: EventoFolhaCatalogo | undefined = CATALOGO_EVENTOS_FOLHA.find((c) => c.codigo === cod);

    // Evita duplicidade do salário mensal se selecionado como 0001 na lista avulsa
    if (cod === '0001') {
      // Ajusta o item base existente caso venha valor customizado ou dias
      const itemBase = itensCalculados.find((i) => i.codigo_evento === '0001');
      if (itemBase && ev.valor_total !== undefined && Number(ev.valor_total) > 0) {
        const vNovo = arredondarMoeda(ev.valor_total);
        totalProventos = totalProventos.minus(salarioProporcional).plus(vNovo);
        itemBase.valor_total = vNovo.toNumber();
        itemBase.memoria_calculo = `Ajustado conforme lançamento avulso: R$ ${vNovo}`;
      }
      continue;
    }

    // Evita duplicidade do INSS ou IRRF se selecionados manualmente (serão apurados com exatidão pelo motor)
    if (cod === '0501' || cod === '0505') {
      continue;
    }

    // Tratamento de Horas Extras 50%
    if (cod === '0010' || ev.tipo === 'hora_extra') {
      const qtd = Number(ev.quantidade || ev.referencia || 0);
      if (qtd > 0) {
        const resHe = calcularHorasExtras(salarioContratual, horasDivisor, qtd, ev.percentual || 50);
        totalProventos = totalProventos.plus(resHe.valor);
        totalVariaveis = totalVariaveis.plus(resHe.valor);
        itensCalculados.push({
          codigo_evento: '0010',
          descricao: `Horas Extras (${ev.percentual || 50}%)`,
          tipo: 'provento',
          referencia: qtd,
          unidade_referencia: 'horas',
          valor_unitario: calcularValorHora(salarioContratual, horasDivisor).times(1.5).toNumber(),
          valor_total: resHe.valor.toNumber(),
          origem: 'calculado',
          incide_inss: 1,
          incide_irrf: 1,
          incide_fgts: 1,
          memoria_calculo: resHe.memoria,
          situacao_validacao: 'HOMOLOGADO',
        });
      }
      continue;
    }

    // Horas Extras 100%
    if (cod === '0011') {
      const qtd = Number(ev.quantidade || ev.referencia || 0);
      if (qtd > 0) {
        const resHe = calcularHorasExtras(salarioContratual, horasDivisor, qtd, 100);
        totalProventos = totalProventos.plus(resHe.valor);
        totalVariaveis = totalVariaveis.plus(resHe.valor);
        itensCalculados.push({
          codigo_evento: '0011',
          descricao: 'Horas Extras 100%',
          tipo: 'provento',
          referencia: qtd,
          unidade_referencia: 'horas',
          valor_unitario: calcularValorHora(salarioContratual, horasDivisor).times(2.0).toNumber(),
          valor_total: resHe.valor.toNumber(),
          origem: 'calculado',
          incide_inss: 1,
          incide_irrf: 1,
          incide_fgts: 1,
          memoria_calculo: resHe.memoria,
          situacao_validacao: 'HOMOLOGADO',
        });
      }
      continue;
    }

    // Adicional Noturno
    if (cod === '0020' || ev.tipo === 'adicional_noturno') {
      const qtd = Number(ev.quantidade || ev.referencia || 0);
      if (qtd > 0) {
        const resNot = calcularAdicionalNoturno(
          salarioContratual,
          horasDivisor,
          qtd,
          ev.percentual || 20,
          ev.reducao_ficta || false,
        );
        totalProventos = totalProventos.plus(resNot.valor);
        totalVariaveis = totalVariaveis.plus(resNot.valor);
        itensCalculados.push({
          codigo_evento: '0020',
          descricao: 'Adicional Noturno (20%)',
          tipo: 'provento',
          referencia: qtd,
          unidade_referencia: 'horas',
          valor_unitario: calcularValorHora(salarioContratual, horasDivisor).times(0.2).toNumber(),
          valor_total: resNot.valor.toNumber(),
          origem: 'calculado',
          incide_inss: 1,
          incide_irrf: 1,
          incide_fgts: 1,
          memoria_calculo: resNot.memoria,
          situacao_validacao: 'HOMOLOGADO',
        });
      }
      continue;
    }

    // Faltas
    if (cod === '0530' || ev.tipo === 'falta') {
      const qtd = Number(ev.quantidade || ev.referencia || 0);
      if (qtd > 0) {
        const resFalta = calcularDescontoFaltas(salarioContratual, qtd, diasMes);
        totalDescontos = totalDescontos.plus(resFalta.valor);
        itensCalculados.push({
          codigo_evento: '0530',
          descricao: 'Faltas Injustificadas',
          tipo: 'desconto',
          referencia: qtd,
          unidade_referencia: 'dias',
          valor_unitario: salarioContratual.dividedBy(diasMes).toNumber(),
          valor_total: resFalta.valor.toNumber(),
          origem: 'calculado',
          incide_inss: 0,
          incide_irrf: 0,
          incide_fgts: 0,
          memoria_calculo: resFalta.memoria,
          situacao_validacao: 'HOMOLOGADO',
        });
      }
      continue;
    }

    // Atrasos
    if (cod === '0532' || ev.tipo === 'atraso') {
      const qtd = Number(ev.quantidade || ev.referencia || 0);
      if (qtd > 0) {
        const resAtraso = calcularDescontoAtrasos(salarioContratual, horasDivisor, qtd);
        totalDescontos = totalDescontos.plus(resAtraso.valor);
        itensCalculados.push({
          codigo_evento: '0532',
          descricao: 'Atrasos / Saídas Antecipadas',
          tipo: 'desconto',
          referencia: qtd,
          unidade_referencia: 'horas',
          valor_unitario: calcularValorHora(salarioContratual, horasDivisor).toNumber(),
          valor_total: resAtraso.valor.toNumber(),
          origem: 'calculado',
          incide_inss: 0,
          incide_irrf: 0,
          incide_fgts: 0,
          memoria_calculo: resAtraso.memoria,
          situacao_validacao: 'HOMOLOGADO',
        });
      }
      continue;
    }

    // Vale-transporte (até 6% do salário-base)
    if (cod === '0510') {
      const limiteVt = arredondarMoeda(salarioContratual.times(0.06));
      const vInformado = toDecimal(ev.valor_total ?? ev.valor ?? limiteVt);
      const vFinal = arredondarMoeda(Decimal.min(vInformado, limiteVt));
      totalDescontos = totalDescontos.plus(vFinal);
      itensCalculados.push({
        codigo_evento: '0510',
        descricao: 'Vale-transporte (Desconto Legal)',
        tipo: 'desconto',
        referencia: 6,
        unidade_referencia: '%',
        valor_unitario: salarioContratual.toNumber(),
        valor_total: vFinal.toNumber(),
        origem: 'calculado',
        incide_inss: 0,
        incide_irrf: 0,
        incide_fgts: 0,
        memoria_calculo: `6% de R$ ${salarioContratual} (limitador legal Lei 7.418/85) = R$ ${vFinal}`,
        situacao_validacao: 'HOMOLOGADO',
      });
      continue;
    }

    // Adiantamento salarial (0520)
    if (cod === '0520') {
      const padraoAdiantamento = arredondarMoeda(salarioContratual.times(0.4));
      const vInformado = toDecimal(ev.valor_total ?? ev.valor ?? 0);
      const vFinal = vInformado.greaterThan(0) ? arredondarMoeda(vInformado) : padraoAdiantamento;
      totalDescontos = totalDescontos.plus(vFinal);
      itensCalculados.push({
        codigo_evento: '0520',
        descricao: 'Adiantamento Salarial',
        tipo: 'desconto',
        referencia: vInformado.greaterThan(0) ? 1 : 40,
        unidade_referencia: vInformado.greaterThan(0) ? 'moeda' : '%',
        valor_unitario: vFinal.toNumber(),
        valor_total: vFinal.toNumber(),
        origem: 'calculado',
        incide_inss: 0,
        incide_irrf: 0,
        incide_fgts: 0,
        memoria_calculo: `Compensação de adiantamento salarial: R$ ${vFinal}`,
        situacao_validacao: 'HOMOLOGADO',
      });
      continue;
    }

    // Eventos genéricos catalogados ou manuais
    const tipoDeterminado = ev.tipo || evCat?.tipo || 'provento';
    const vTotal = arredondarMoeda(toDecimal(ev.valor_total ?? ev.valor ?? 0));

    if (vTotal.greaterThan(0)) {
      if (tipoDeterminado === 'provento') {
        totalProventos = totalProventos.plus(vTotal);
      } else if (tipoDeterminado === 'desconto') {
        totalDescontos = totalDescontos.plus(vTotal);
      }

      itensCalculados.push({
        codigo_evento: cod || (tipoDeterminado === 'provento' ? '0075' : '0520'),
        descricao: ev.descricao || evCat?.evento || (tipoDeterminado === 'provento' ? 'Provento Avulso' : 'Desconto Avulso'),
        tipo: tipoDeterminado as any,
        referencia: Number(ev.referencia || 1),
        unidade_referencia: ev.unidade_referencia || evCat?.unidade_referencia || 'moeda',
        valor_unitario: vTotal.toNumber(),
        valor_total: vTotal.toNumber(),
        origem: 'manual',
        incide_inss: ev.incide_inss !== undefined ? ev.incide_inss : (evCat ? evCat.inss : (tipoDeterminado === 'provento' ? 1 : 0)),
        incide_irrf: ev.incide_irrf !== undefined ? ev.incide_irrf : (evCat ? evCat.irrf : (tipoDeterminado === 'provento' ? 1 : 0)),
        incide_fgts: ev.incide_fgts !== undefined ? ev.incide_fgts : (evCat ? evCat.fgts : (tipoDeterminado === 'provento' ? 1 : 0)),
        memoria_calculo: ev.memoria_calculo || `${evCat?.evento || 'Lançamento'}: R$ ${vTotal}`,
        situacao_validacao: evCat?.situacao_validacao || 'HOMOLOGADO',
      });
    }
  }

  // 3. DSR sobre variáveis (se houver HE ou Noturno)
  if (totalVariaveis.greaterThan(0)) {
    const resDsr = calcularDsrSobreVariaveis(totalVariaveis);
    totalProventos = totalProventos.plus(resDsr.valor);
    itensCalculados.push({
      codigo_evento: '0012',
      descricao: 'DSR sobre Horas Extras / Noturno',
      tipo: 'provento',
      referencia: 5,
      unidade_referencia: 'dias',
      valor_unitario: resDsr.valor.dividedBy(5).toNumber(),
      valor_total: resDsr.valor.toNumber(),
      origem: 'calculado',
      incide_inss: 1,
      incide_irrf: 1,
      incide_fgts: 1,
      memoria_calculo: resDsr.memoria,
      situacao_validacao: 'HOMOLOGADO',
    });
  }

  // 4. Apuração das Bases Legais (INSS e FGTS)
  let baseInss = new Decimal('0.00');
  let baseFgts = new Decimal('0.00');

  for (const it of itensCalculados) {
    if (it.tipo === 'provento') {
      if (it.incide_inss === 1) {
        baseInss = baseInss.plus(toDecimal(it.valor_total));
      }
      if (it.incide_fgts === 1) {
        baseFgts = baseFgts.plus(toDecimal(it.valor_total));
      }
    } else if (it.tipo === 'desconto') {
      // Faltas reduzem a base de INSS
      if (it.codigo_evento === '0530' || it.codigo_evento === '0532') {
        baseInss = Decimal.max(0, baseInss.minus(toDecimal(it.valor_total)));
        baseFgts = Decimal.max(0, baseFgts.minus(toDecimal(it.valor_total)));
      }
    }
  }

  baseInss = arredondarMoeda(baseInss);
  baseFgts = arredondarMoeda(baseFgts);

  // 5. Cálculo Progressivo do INSS (0501)
  const resInss = calcularInssProgressivo(baseInss);
  if (resInss.valor.greaterThan(0)) {
    totalDescontos = totalDescontos.plus(resInss.valor);
    itensCalculados.push({
      codigo_evento: '0501',
      descricao: 'INSS (Faixas Progressivas)',
      tipo: 'desconto',
      referencia: 0,
      unidade_referencia: '%',
      valor_unitario: baseInss.toNumber(),
      valor_total: resInss.valor.toNumber(),
      origem: 'calculado',
      incide_inss: 0,
      incide_irrf: 0,
      incide_fgts: 0,
      memoria_calculo: resInss.memoria,
      situacao_validacao: 'HOMOLOGADO',
    });
  }

  // 6. Cálculo Progressivo do IRRF (0505)
  const resIrrf = calcularIrrfProgressivo(baseInss, resInss.valor, numDependentes);
  if (resIrrf.valor.greaterThan(0)) {
    totalDescontos = totalDescontos.plus(resIrrf.valor);
    itensCalculados.push({
      codigo_evento: '0505',
      descricao: 'IRRF (Retenção na Fonte)',
      tipo: 'desconto',
      referencia: numDependentes,
      unidade_referencia: 'dep',
      valor_unitario: resIrrf.baseLiquida.toNumber(),
      valor_total: resIrrf.valor.toNumber(),
      origem: 'calculado',
      incide_inss: 0,
      incide_irrf: 0,
      incide_fgts: 0,
      memoria_calculo: resIrrf.memoria,
      situacao_validacao: 'HOMOLOGADO',
    });
  }

  // 7. Depósito de FGTS Informativo (0904)
  const fgtsInformativo = calcularFgtsInformativo(baseFgts);
  itensCalculados.push({
    codigo_evento: '0904',
    descricao: 'FGTS do Mês (Depósito 8% - Informativo)',
    tipo: 'informativo',
    referencia: 8,
    unidade_referencia: '%',
    valor_unitario: baseFgts.toNumber(),
    valor_total: fgtsInformativo.toNumber(),
    origem: 'calculado',
    incide_inss: 0,
    incide_irrf: 0,
    incide_fgts: 0,
    memoria_calculo: `8% sobre base FGTS R$ ${baseFgts} = R$ ${fgtsInformativo} (sem desconto)`,
    situacao_validacao: 'HOMOLOGADO',
  });

  // 8. Salário Líquido Final
  const salarioLiquido = arredondarMoeda(Decimal.max(0, totalProventos.minus(totalDescontos)));

  return {
    salario_base_contratual: salarioContratual.toNumber(),
    salario_base_proporcional: salarioProporcional.toNumber(),
    dias_trabalhados: diasTrabalhados.toNumber(),
    dias_mes: diasMes,
    horas_mensais_divisor: horasDivisor,
    total_proventos: totalProventos.toNumber(),
    total_descontos: totalDescontos.toNumber(),
    salario_liquido: salarioLiquido.toNumber(),
    base_inss: baseInss.toNumber(),
    base_irrf: resIrrf.baseLiquida.toNumber(),
    base_fgts: baseFgts.toNumber(),
    valor_fgts_informativo: fgtsInformativo.toNumber(),
    itens: itensCalculados,
  };
}
