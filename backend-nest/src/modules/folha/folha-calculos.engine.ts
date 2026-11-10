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
  } catch {
    return new Decimal('0.00');
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

