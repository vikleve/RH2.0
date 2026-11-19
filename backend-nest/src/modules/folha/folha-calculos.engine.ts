import { Decimal } from 'decimal.js';

// Configura precisão e modo de arredondamento ROUND_HALF_UP
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
  } catch (err) {
    throw new Error(`[RF-FIN-001] Valor monetário inválido para conversão Decimal: "${val}"`);
  }
}

export function arredondarMoeda(val: any): Decimal {
  return toDecimal(val).toDecimalPlaces(2, Decimal.ROUND_HALF_UP);
}

export const TABELA_INSS_PADRAO_2026 = [
  { min: new Decimal('0.00'), max: new Decimal('1518.00'), aliq: new Decimal('7.5') },
  { min: new Decimal('1518.01'), max: new Decimal('2793.88'), aliq: new Decimal('9.0') },
  { min: new Decimal('2793.89'), max: new Decimal('4190.83'), aliq: new Decimal('12.0') },
  { min: new Decimal('4190.84'), max: new Decimal('8157.41'), aliq: new Decimal('14.0') },
];
export const TETO_INSS_PADRAO_2026 = new Decimal('8157.41');

export const TABELA_IRRF_PADRAO_2026 = [
  { min: new Decimal('0.00'), max: new Decimal('2259.20'), aliq: new Decimal('0.0'), ded: new Decimal('0.00') },
  { min: new Decimal('2259.21'), max: new Decimal('2826.65'), aliq: new Decimal('7.5'), ded: new Decimal('169.44') },
  { min: new Decimal('2826.66'), max: new Decimal('3751.05'), aliq: new Decimal('15.0'), ded: new Decimal('381.44') },
  { min: new Decimal('3751.06'), max: new Decimal('4664.68'), aliq: new Decimal('22.5'), ded: new Decimal('662.77') },
  { min: new Decimal('4664.69'), max: null, aliq: new Decimal('27.5'), ded: new Decimal('896.00') },
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
): { valor: Decimal; memoria: string } {
  let base = toDecimal(baseCalculo);
  if (base.greaterThan(teto)) {
    base = teto;
  }
  let totalInss = new Decimal('0.00');
  const partes: string[] = [];

  for (const faixa of TABELA_INSS_PADRAO_2026) {
    if (base.lessThan(faixa.min)) continue;
    const limiteSuperior = faixa.max && base.greaterThan(faixa.max) ? faixa.max : base;
    const baseFaixa = limiteSuperior.minus(faixa.min);
    if (baseFaixa.greaterThan(0)) {
      const valorFaixa = baseFaixa.times(faixa.aliq).dividedBy(100);
      totalInss = totalInss.plus(valorFaixa);
      partes.push(`Faixa ${faixa.aliq}%: R$ ${arredondarMoeda(valorFaixa)}`);
    }
  }

  const finalInss = arredondarMoeda(totalInss);
  const memoria = `INSS Progressivo sobre R$ ${arredondarMoeda(base)}: ${partes.join(' + ')} = R$ ${finalInss}`;
  return { valor: finalInss, memoria };
}

export function calcularIrrfProgressivo(
  baseCalculoBruta: any,
  inssDescontado: any = 0,
  dependentes = 0,
  deducaoPorDependente = DEDUCAO_DEPENDENTE_IRRF_PADRAO,
): { valor: Decimal; memoria: string } {
  const bruta = toDecimal(baseCalculoBruta);
  const inss = toDecimal(inssDescontado);
  const dedDep = toDecimal(dependentes).times(toDecimal(deducaoPorDependente));
  const baseLiquida = bruta.minus(inss).minus(dedDep);

  if (baseLiquida.lessThanOrEqualTo(0)) {
    return { valor: new Decimal('0.00'), memoria: 'Base líquida de IRRF zerada ou negativa.' };
  }

  let faixaAplicada: any = null;
  for (const f of TABELA_IRRF_PADRAO_2026) {
    if (f.max === null || baseLiquida.lessThanOrEqualTo(f.max)) {
      faixaAplicada = f;
      break;
    }
  }

  if (!faixaAplicada || faixaAplicada.aliq.isZero()) {
    return { valor: new Decimal('0.00'), memoria: `Isento de IRRF (Base: R$ ${arredondarMoeda(baseLiquida)})` };
  }

  const impostoBruto = baseLiquida.times(faixaAplicada.aliq).dividedBy(100);
  const impostoLiquido = impostoBruto.minus(faixaAplicada.ded);
  const valorFinal = arredondarMoeda(Decimal.max(impostoLiquido, new Decimal('0.00')));
  const memoria = `IRRF (${faixaAplicada.aliq}% sobre base líquida R$ ${arredondarMoeda(baseLiquida)}) - parcela R$ ${faixaAplicada.ded} = R$ ${valorFinal}`;
  return { valor: valorFinal, memoria };
}

export function calcularFgtsInformativo(baseCalculo: any, aliquota = ALIQUOTA_FGTS_PADRAO): Decimal {
  const base = toDecimal(baseCalculo);
  return arredondarMoeda(base.times(aliquota).dividedBy(100));
}

export function calcularInsalubridade(grauOuPerc: any = 20, salarioMinimo = new Decimal('1518.00')): { valor: Decimal; memoria: string } {
  const sm = toDecimal(salarioMinimo);
  const ref = toDecimal(grauOuPerc);
  let perc = new Decimal(20);
  if (ref.equals(1) || ref.equals(10)) perc = new Decimal(10);
  else if (ref.equals(3) || ref.equals(40)) perc = new Decimal(40);
  const valor = arredondarMoeda(sm.times(perc).dividedBy(100));
  return { valor, memoria: `Insalubridade (${perc}% sobre Salário Mínimo R$ ${sm}): R$ ${valor}` };
}

export function calcularPericulosidade(salarioBase: any, percentual = 30): { valor: Decimal; memoria: string } {
  const sb = toDecimal(salarioBase);
  const perc = toDecimal(percentual);
  const valor = arredondarMoeda(sb.times(perc).dividedBy(100));
  return { valor, memoria: `Periculosidade (${perc}% sobre Salário Base R$ ${sb}): R$ ${valor}` };
}

export function calcularFeriasGozadas(salarioBase: any, dias = 30): { valor: Decimal; memoria: string } {
  const sb = toDecimal(salarioBase);
  const d = toDecimal(dias);
  const valor = arredondarMoeda(sb.dividedBy(30).times(d));
  return { valor, memoria: `Férias (${d} dias): R$ ${valor}` };
}

export function calcularTercoConstitucional(baseFerias: any): { valor: Decimal; memoria: string } {
  const base = toDecimal(baseFerias);
  const valor = arredondarMoeda(base.dividedBy(3));
  return { valor, memoria: `1/3 Constitucional de Férias: R$ ${valor}` };
}

export function calcularDecimoTerceiro(salarioBase: any, avos = 12, parcela = 1, adiantamento = 0): { valor: Decimal; memoria: string } {
  const sb = toDecimal(salarioBase);
  const av = toDecimal(avos);
  const integral = sb.dividedBy(12).times(av);
  if (parcela === 1) {
    const valor = arredondarMoeda(integral.times(0.5));
    return { valor, memoria: `13º Salário 1ª Parcela (${av}/12 avos): R$ ${valor}` };
  } else {
    const valor = arredondarMoeda(Decimal.max(0, integral.minus(toDecimal(adiantamento))));
    return { valor, memoria: `13º Salário 2ª Parcela (${av}/12 avos - adiantamento): R$ ${valor}` };
  }
}

export function calcularSalarioFamilia(salarioBase: any, dependentes = 0, teto = new Decimal('1906.00'), cota = new Decimal('65.00')): { valor: Decimal; memoria: string } {
  const sb = toDecimal(salarioBase);
  const dep = Number(dependentes);
  if (dep <= 0 || sb.greaterThan(teto)) {
    return { valor: new Decimal('0.00'), memoria: `Salário-família não elegível (Salário R$ ${sb} > Teto R$ ${teto})` };
  }
  const valor = arredondarMoeda(toDecimal(cota).times(dep));
  return { valor, memoria: `Salário-família: ${dep} cotas x R$ ${cota} = R$ ${valor}` };
}

export function calcularAvisoPrevioIndenizado(salarioBase: any, anosServico = 0): { valor: Decimal; dias: number; memoria: string } {
  const sb = toDecimal(salarioBase);
  const anos = Math.max(0, Number(anosServico));
  const dias = Math.min(90, 30 + anos * 3);
  const valor = arredondarMoeda(sb.dividedBy(30).times(dias));
  return { valor, dias, memoria: `Aviso prévio indenizado (${dias} dias): R$ ${valor}` };
}

export function calcularValeTransporte(salarioBase: any, custoTotal: any = null, maxPerc = 6): { valor: Decimal; memoria: string } {
  const sb = toDecimal(salarioBase);
  const tetoLegal = arredondarMoeda(sb.times(maxPerc).dividedBy(100));
  if (custoTotal !== null && custoTotal !== undefined) {
    const custo = toDecimal(custoTotal);
    const valor = Decimal.min(tetoLegal, custo);
    return { valor, memoria: `VT: menor entre custo R$ ${custo} e teto 6% R$ ${tetoLegal} = R$ ${valor}` };
  }
  return { valor: tetoLegal, memoria: `VT 6% sobre salário base R$ ${sb} = R$ ${tetoLegal}` };
}

export function calcularEncargosPatronais(baseInss: any, aliqPatronal = 20, aliqRat = 2, fap = 1, aliqTerceiros = 5.8) {
  const base = toDecimal(baseInss);
  const inssPatronal = arredondarMoeda(base.times(aliqPatronal).dividedBy(100));
  const ratFap = arredondarMoeda(base.times(toDecimal(aliqRat).times(toDecimal(fap))).dividedBy(100));
  const terceiros = arredondarMoeda(base.times(aliqTerceiros).dividedBy(100));
  return {
    inssPatronal,
    ratFap,
    terceiros,
    total: inssPatronal.plus(ratFap).plus(terceiros),
  };
}


