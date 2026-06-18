"""
test_bootstrap.py — Testes automatizados do bootstrapping de curva zero-cupom.

Cobertura:
  - R5 (obrigatório): re-precificação com erro máximo < 1E-4
  - Contagem de dias úteis
  - Geração de fluxos de caixa (LTN e NTN-F)
  - Resolução via substituição progressiva (forward substitution)
  - Sanity check: taxa spot da LTN deve coincidir com Tx. Indicativa do TXT

Executar com:
    pytest test_bootstrap.py -v
"""

import datetime
import math
import pytest

from bootstrapping import (
    parse_float_br,
    count_business_days,
    generate_cash_flows,
    forward_substitution,
    build_system,
    compute_spot_curve,
    repricing_error,
    filter_triangular_bonds,
)

# ---------------------------------------------------------------------------
# FIXTURES — Exemplo mínimo do PDF (data-base 2026-06-01)
# ---------------------------------------------------------------------------

BASE_DATE = datetime.date(2026, 6, 1)

# Feriados reais do período (extraídos do calendário ANBIMA para o intervalo
# 2026-06-01 → 2027-01-01). Ajuste se usar o arquivo real.
HOLIDAYS: set = set()  # sem feriados no período do exemplo

BONDS_EXAMPLE = [
    {
        'tipo': 'LTN',
        'vencimento': datetime.date(2026, 7, 1),
        'pu': 988.866252,
    },
    {
        'tipo': 'LTN',
        'vencimento': datetime.date(2026, 10, 1),
        'pu': 956.259296,
    },
    {
        'tipo': 'NTN-F',
        'vencimento': datetime.date(2027, 1, 1),
        'emissao': datetime.date(2016, 1, 15),
        'pu': 1019.143414,
    },
]

# Saída esperada pelo gabarito do PDF
EXPECTED_CURVE = [
    {"data": "2026-07-01", "du": 21,  "prazo_anos": 0.083333, "fator_desconto": 0.988866, "taxa_spot": 0.143798},
    {"data": "2026-10-01", "du": 86,  "prazo_anos": 0.341270, "fator_desconto": 0.956259, "taxa_spot": 0.140034},
    {"data": "2027-01-01", "du": 148, "prazo_anos": 0.587302, "fator_desconto": 0.925696, "taxa_spot": 0.140498},
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def build_example_system():
    """Monta C, P e payment_dates a partir do exemplo do PDF."""
    return build_system(BONDS_EXAMPLE, BASE_DATE, HOLIDAYS)


# ---------------------------------------------------------------------------
# 1. Utilitários de parsing
# ---------------------------------------------------------------------------

class TestParseFloatBr:
    def test_comma_decimal(self):
        assert parse_float_br("988,866252") == pytest.approx(988.866252)

    def test_dot_thousand_comma_decimal(self):
        assert parse_float_br("1.019,143414") == pytest.approx(1019.143414)

    def test_plain_float(self):
        assert parse_float_br("1000.0") == pytest.approx(1000.0)

    def test_strips_whitespace(self):
        assert parse_float_br("  956,259296  ") == pytest.approx(956.259296)


# ---------------------------------------------------------------------------
# 2. Contagem de dias úteis
# ---------------------------------------------------------------------------

class TestCountBusinessDays:
    def test_ltn_jul_no_holidays(self):
        # 2026-06-01 → 2026-07-01: 21 DU (gabarito PDF)
        assert count_business_days(BASE_DATE, datetime.date(2026, 7, 1), HOLIDAYS) == 21

    def test_ltn_oct_no_holidays(self):
        # 2026-06-01 → 2026-10-01: 86 DU (gabarito PDF)
        assert count_business_days(BASE_DATE, datetime.date(2026, 10, 1), HOLIDAYS) == 86

    def test_ntnf_jan_no_holidays(self):
        # 2026-06-01 → 2027-01-01: 148 DU (gabarito PDF)
        assert count_business_days(BASE_DATE, datetime.date(2027, 1, 1), HOLIDAYS) == 148

    def test_same_date_returns_zero(self):
        assert count_business_days(BASE_DATE, BASE_DATE, HOLIDAYS) == 0

    def test_weekend_not_counted(self):
        # 2026-06-06 (sábado) e 2026-06-07 (domingo) não contam
        monday = datetime.date(2026, 6, 8)
        friday = datetime.date(2026, 6, 5)
        # de sexta a segunda: apenas segunda = 1 DU
        assert count_business_days(friday, monday, HOLIDAYS) == 1

    def test_holiday_excluded(self):
        holiday = datetime.date(2026, 6, 4)  # quinta
        thursday = datetime.date(2026, 6, 3)
        friday   = datetime.date(2026, 6, 5)
        # sem feriado: 2 DU (qui e sex); com feriado qui: 1 DU (só sex)
        assert count_business_days(thursday, friday, {holiday}) == 0


# ---------------------------------------------------------------------------
# 3. Geração de fluxos de caixa
# ---------------------------------------------------------------------------

class TestGenerateCashFlows:
    def test_ltn_single_flow(self):
        bond = BONDS_EXAMPLE[0]  # LTN 2026-07-01
        flows = generate_cash_flows(bond, BASE_DATE)
        assert flows == {datetime.date(2026, 7, 1): 1000.0}

    def test_ntnf_maturity_value(self):
        bond = BONDS_EXAMPLE[2]  # NTN-F 2027-01-01
        flows = generate_cash_flows(bond, BASE_DATE)
        assert flows[datetime.date(2027, 1, 1)] == pytest.approx(1048.8088)

    def test_ntnf_coupon_jul(self):
        bond = BONDS_EXAMPLE[2]
        flows = generate_cash_flows(bond, BASE_DATE)
        assert datetime.date(2026, 7, 1) in flows
        assert flows[datetime.date(2026, 7, 1)] == pytest.approx(48.8088)

    def test_ntnf_no_past_flows(self):
        """Nenhum fluxo deve estar em data <= base_date."""
        bond = BONDS_EXAMPLE[2]
        flows = generate_cash_flows(bond, BASE_DATE)
        for dt in flows:
            assert dt > BASE_DATE

    def test_ntnf_exactly_two_future_flows(self):
        """Para a NTN-F do exemplo há exatamente 2 fluxos futuros: jul/26 e jan/27."""
        bond = BONDS_EXAMPLE[2]
        flows = generate_cash_flows(bond, BASE_DATE)
        assert len(flows) == 2

    def test_unknown_type_raises(self):
        bond = {'tipo': 'XYZ', 'vencimento': datetime.date(2027, 1, 1)}
        with pytest.raises(ValueError, match="desconhecido"):
            generate_cash_flows(bond, BASE_DATE)


# ---------------------------------------------------------------------------
# 4. Forward substitution
# ---------------------------------------------------------------------------

class TestForwardSubstitution:
    def test_identity_matrix(self):
        C = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        P = [1.0, 2.0, 3.0]
        d = forward_substitution(C, P)
        assert d == pytest.approx([1.0, 2.0, 3.0])

    def test_lower_triangular(self):
        # C = [[2, 0], [3, 4]], P = [4, 11]  =>  d = [2, 1.25]
        C = [[2.0, 0.0], [3.0, 4.0]]
        P = [4.0, 11.0]
        d = forward_substitution(C, P)
        assert d == pytest.approx([2.0, 1.25])

    def test_singular_raises(self):
        C = [[0.0, 0.0], [1.0, 2.0]]
        P = [1.0, 2.0]
        with pytest.raises(ZeroDivisionError):
            forward_substitution(C, P)


# ---------------------------------------------------------------------------
# 5. Sistema completo — R5: re-precificação
# ---------------------------------------------------------------------------

class TestRepricing:
    """
    R5 — REQUISITO OBRIGATÓRIO do desafio:
    Re-precificar cada título usando a curva gerada deve resultar em
    erro máximo absoluto < 1E-4.
    """

    def test_repricing_error_below_tolerance(self):
        C, P, payment_dates = build_example_system()
        d = forward_substitution(C, P)
        error = repricing_error(C, d, P)
        assert error < 1e-4, (
            f"Erro de re-precificação {error:.2e} excede a tolerância 1E-4. "
            f"A curva gerada não reproduz os preços de mercado."
        )

    def test_repricing_error_is_essentially_zero(self):
        """Para um sistema exato, o erro deve ser numericamente próximo de zero."""
        C, P, payment_dates = build_example_system()
        d = forward_substitution(C, P)
        error = repricing_error(C, d, P)
        assert error < 1e-8

    def test_each_bond_repriced_individually(self):
        """Verifica o erro por título, não só o máximo."""
        C, P, payment_dates = build_example_system()
        d = forward_substitution(C, P)
        for i in range(len(P)):
            predicted = sum(C[i][j] * d[j] for j in range(len(d)))
            err = abs(predicted - P[i])
            assert err < 1e-4, (
                f"Título {i} (venc. {payment_dates[i].isoformat()}): "
                f"erro {err:.2e} excede 1E-4"
            )


# ---------------------------------------------------------------------------
# 6. Sanity checks da curva — gabarito do PDF
# ---------------------------------------------------------------------------

class TestCurveValues:
    def setup_method(self):
        C, P, payment_dates = build_example_system()
        d = forward_substitution(C, P)
        self.curva = compute_spot_curve(d, payment_dates, BASE_DATE, HOLIDAYS)

    def test_number_of_vertices(self):
        assert len(self.curva) == 3

    def test_du_ltn_jul(self):
        assert self.curva[0]["du"] == 21

    def test_du_ltn_oct(self):
        assert self.curva[1]["du"] == 86

    def test_du_ntnf_jan(self):
        assert self.curva[2]["du"] == 148

    def test_fator_desconto_ltn_jul(self):
        # Para LTN: fator = PU / 1000
        assert self.curva[0]["fator_desconto"] == pytest.approx(988.866252 / 1000, rel=1e-4)

    def test_fator_desconto_ltn_oct(self):
        assert self.curva[1]["fator_desconto"] == pytest.approx(956.259296 / 1000, rel=1e-4)

    def test_taxa_spot_ltn_jul_matches_indicativa(self):
        """
        Sanity check do PDF: para LTN (zero-cupom), a taxa spot deve
        coincidir com a Tx. Indicativa do TXT (14,3798% = 0.143798).
        """
        assert self.curva[0]["taxa_spot"] == pytest.approx(0.143798, rel=1e-3)

    def test_taxa_spot_ltn_oct_matches_indicativa(self):
        assert self.curva[1]["taxa_spot"] == pytest.approx(0.140034, rel=1e-3)

    def test_taxa_spot_ntnf_jan(self):
        # Valor de referência do gabarito do PDF
        assert self.curva[2]["taxa_spot"] == pytest.approx(0.140498, rel=1e-3)

    def test_discount_factors_decreasing(self):
        """Fatores de desconto devem ser decrescentes com o prazo."""
        fatores = [v["fator_desconto"] for v in self.curva]
        assert fatores == sorted(fatores, reverse=True)

    def test_spot_rates_positive(self):
        for v in self.curva:
            assert v["taxa_spot"] > 0


# ---------------------------------------------------------------------------
# 7. filter_triangular_bonds
# ---------------------------------------------------------------------------

class TestFilterTriangularBonds:
    def test_example_returns_three_bonds(self):
        selected = filter_triangular_bonds(BONDS_EXAMPLE, BASE_DATE)
        assert len(selected) == 3

    def test_ntnf_rejected_if_coupon_date_missing(self):
        """NTN-F cujo cupom cai em data não coberta por LTN deve ser rejeitada."""
        bonds = [
            # Apenas uma LTN: cobre 2026-07-01
            {'tipo': 'LTN', 'vencimento': datetime.date(2026, 7, 1), 'pu': 988.0},
            # NTN-F com cupom em 2026-07-01 (ok) e 2027-01-01 (ok = vencimento),
            # mas sem LTN cobrindo 2026-07-01 já está no set — isso passa.
            # Aqui testamos uma NTN-F cujo cupom intermediário NÃO está no set.
            {
                'tipo': 'NTN-F',
                'vencimento': datetime.date(2027, 7, 1),  # cupom em jan/27 — não coberto
                'emissao': datetime.date(2016, 1, 15),
                'pu': 1020.0,
            },
        ]
        selected = filter_triangular_bonds(bonds, BASE_DATE)
        # A NTN-F deve ser rejeitada: jan/27 não está em known_dates
        tipos = [b['tipo'] for b in selected]
        assert 'NTN-F' not in tipos
