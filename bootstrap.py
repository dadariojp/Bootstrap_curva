import datetime
import json
import re
import sys
import csv
from typing import List, Dict, Set, Tuple

# ------------------------------------------------------------
# PARTE 1: UTILITÁRIOS DE DATA
# ------------------------------------------------------------

def parse_float_br(s: str) -> float:
    """
    Converte string com formato brasileiro (vírgula decimal, ponto milhar) para float.
    Ex: "988,866252" -> 988.866252
        "1.019,143414" -> 1019.143414
    """
    s = s.strip()
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    return float(s)

def parse_date_br(date_str: str) -> datetime.date:
    """Converte string YYYYMMDD ou YYYY-MM-DD para date."""
    date_str = date_str.strip().replace('-', '')
    return datetime.date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))

def is_business_day(date: datetime.date, holidays: Set[datetime.date]) -> bool:
    return date.weekday() < 5 and date not in holidays

def count_business_days(start: datetime.date, end: datetime.date, holidays: Set[datetime.date]) -> int:
    """Conta dias úteis entre start (exclusive) e end (inclusive)."""
    if start >= end:
        return 0
    current = start + datetime.timedelta(days=1)
    count = 0
    while current <= end:
        if is_business_day(current, holidays):
            count += 1
        current += datetime.timedelta(days=1)
    return count

# ------------------------------------------------------------
# PARTE 2: LEITURA DOS ARQUIVOS
# ------------------------------------------------------------

def _parse_date_token(token: str) -> datetime.date | None:
    """
    Tenta converter um token de string em um objeto date.
    Suporta: DD/MM/YYYY, YYYYMMDD, YYYY-MM-DD, DD-MM-YYYY, M/D/YYYY.
    Retorna None se nenhum formato funcionar.
    """
    formats = [
        "%d/%m/%Y",   # 25/12/2026  (padrão BR)
        "%m/%d/%Y",   # 12/25/2026  (padrão ANBIMA CSV)
        "%Y%m%d",     # 20261225
        "%Y-%m-%d",   # 2026-12-25
        "%d-%m-%Y",   # 25-12-2026
    ]
    for fmt in formats:
        try:
            return datetime.datetime.strptime(token, fmt).date()
        except ValueError:
            continue
    return None


def load_holidays(filepath: str) -> Set[datetime.date]:
    """
    Carrega feriados do arquivo de feriados da ANBIMA.

    Suporta três formatos:
      - .xls  : planilha Excel (lida com xlrd); a data pode estar como
                número serial do Excel ou como texto.
      - .csv  : CSV com separador vírgula; a data é lida na primeira coluna.
      - .txt  : arquivo texto linha a linha; a data é o primeiro token de
                cada linha.

    Retorna um set de datetime.date, sem duplicatas.
    """
    holidays: Set[datetime.date] = set()

    if filepath.lower().endswith('.xls'):
        import xlrd  # pip install xlrd
        workbook = xlrd.open_workbook(filepath)
        sheet = workbook.sheet_by_index(0)
        for row_idx in range(sheet.nrows):
            cell = sheet.cell(row_idx, 0)
            if cell.ctype == xlrd.XL_CELL_DATE:
                dt_tuple = xlrd.xldate_as_tuple(cell.value, workbook.datemode)
                holidays.add(datetime.date(dt_tuple[0], dt_tuple[1], dt_tuple[2]))
            elif cell.ctype == xlrd.XL_CELL_TEXT:
                parsed = _parse_date_token(cell.value.strip())
                if parsed is not None:
                    holidays.add(parsed)

    elif filepath.lower().endswith('.csv'):
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            reader = csv.reader(f)
            next(reader, None)  # pula cabeçalho
            for row in reader:
                if not row:
                    continue
                token = row[0].strip()
                parsed = _parse_date_token(token)
                if parsed is not None:
                    holidays.add(parsed)

    else:  # .txt ou qualquer outro formato texto
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                raw = line.strip()
                if not raw:
                    continue
                token = raw.split()[0].replace(';', '').replace(',', '').strip()
                parsed = _parse_date_token(token)
                if parsed is not None:
                    holidays.add(parsed)

    return holidays


def parse_bonds(filepath: str) -> Tuple[datetime.date, List[Dict]]:
    """
    Lê o arquivo TXT da ANBIMA (separado por @).
    Lida com cabeçalho quebrado em várias linhas.
    Retorna (data_base, lista_de_titulos).
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        raw_lines = [line.strip() for line in f if line.strip()]

    cleaned_lines = [line.replace('→', '').replace('\\', '').strip() for line in raw_lines if line]

    if not cleaned_lines:
        raise ValueError("Arquivo vazio.")

    # Localiza o cabeçalho: linha que contém 'Titulo' (e idealmente 'PU' também)
    header_idx = None
    for i, line in enumerate(cleaned_lines):
        if 'Titulo' in line and 'PU' in line:
            header_idx = i
            break

    if header_idx is None:
        for i, line in enumerate(cleaned_lines):
            if 'Titulo' in line:
                header_idx = i
                break

    if header_idx is None:
        raise ValueError("Linha com 'Titulo' não encontrada no arquivo.")

    # Concatena linhas seguintes até o cabeçalho ter campos suficientes (>=10 @)
    header_line = cleaned_lines[header_idx]
    data_start = header_idx + 1
    while data_start < len(cleaned_lines) and header_line.count('@') < 10:
        header_line += cleaned_lines[data_start]
        data_start += 1

    # Identifica colunas pelo cabeçalho
    header_parts = header_line.split('@')
    col_titulo = col_venc = col_emissao = col_pu = None
    for i, col in enumerate(header_parts):
        norm = col.strip().lower().replace('ã', 'a').replace('í', 'i').replace('ç', 'c')
        if 'titulo' in norm:
            col_titulo = i
        elif 'vencimento' in norm:
            col_venc = i
        elif 'emissao' in norm or 'base/emissao' in norm:
            col_emissao = i
        elif norm == 'pu':
            col_pu = i

    if any(v is None for v in [col_titulo, col_venc, col_pu]):
        raise ValueError(f"Colunas obrigatórias não encontradas. Cabeçalho: {header_parts}")

    bonds = []
    base_date = None

    for line in cleaned_lines[data_start:]:
        if not line or '@' not in line:
            continue
        parts = line.split('@')
        if len(parts) <= max(col_titulo, col_venc, col_pu):
            continue

        tipo = parts[col_titulo].strip()
        if tipo not in ['LTN', 'NTN-F']:
            continue

        venc_str = parts[col_venc].strip()
        pu_str   = parts[col_pu].strip()

        try:
            pu        = parse_float_br(pu_str)
            vencimento = parse_date_br(venc_str)
        except ValueError:
            continue

        emissao = None
        if col_emissao is not None and len(parts) > col_emissao:
            emis_str = parts[col_emissao].strip()
            if emis_str:
                try:
                    emissao = parse_date_br(emis_str)
                except ValueError:
                    pass

        if base_date is None and len(parts) > 1:
            try:
                base_date = parse_date_br(parts[1].strip())
            except ValueError:
                pass

        bond = {'tipo': tipo, 'vencimento': vencimento, 'pu': pu}
        if emissao:
            bond['emissao'] = emissao
        bonds.append(bond)

    if base_date is None:
        for line in cleaned_lines:
            for token in line.split('@'):
                t = token.strip()
                if len(t) == 8 and t.isdigit():
                    try:
                        base_date = parse_date_br(t)
                        break
                    except ValueError:
                        pass
            if base_date:
                break

    if base_date is None:
        raise ValueError("Data base não encontrada no arquivo.")

    return base_date, bonds

# ------------------------------------------------------------
# PARTE 3: GERAÇÃO DOS FLUXOS DE CAIXA
# ------------------------------------------------------------

def generate_cash_flows(bond: Dict, base_date: datetime.date) -> Dict[datetime.date, float]:
    """
    Gera o mapa {data -> valor_futuro} para um título.
    Para NTN-F, percorre as datas de cupom de trás para frente a partir
    do vencimento (sempre 1-jan ou 1-jul), garantindo que nenhuma data
    de pagamento seja omitida.
    """
    tipo     = bond['tipo']
    maturity = bond['vencimento']
    flows    = {}

    if tipo == 'LTN':
        flows[maturity] = 1000.0

    elif tipo == 'NTN-F':
        coupon = 48.8088

        # Principal + último cupom sempre no vencimento
        flows[maturity] = 1048.8088

        # Percorre para trás de 6 em 6 meses (Jan↔Jul) a partir do vencimento
        current = maturity
        while True:
            if current.month == 1:
                current = datetime.date(current.year - 1, 7, 1)
            else:  # month == 7
                current = datetime.date(current.year, 1, 1)

            if current <= base_date:
                break
            flows[current] = coupon

    else:
        raise ValueError(f"Tipo de título desconhecido: {tipo}")

    return flows

# ------------------------------------------------------------
# PARTE 4: SELEÇÃO DE TÍTULOS (MATRIZ TRIANGULAR)
# ------------------------------------------------------------

def filter_triangular_bonds(bonds: List[Dict], base_date: datetime.date) -> List[Dict]:
    """
    Seleciona o subconjunto de títulos que produz matriz C quadrada e triangular inferior.

    Regras de aceitação de uma NTN-F:
      1. Seu vencimento NÃO pode já estar em known_dates (evita duplicata de coluna).
      2. Deve ter pelo menos um cupom futuro (não é zero-cupom disfarçado).
      3. Todos os seus cupons futuros devem estar em known_dates (garante triangularidade).

    Cada título aceito adiciona exatamente uma nova data (seu vencimento) → matriz quadrada.
    """
    ltns  = sorted([b for b in bonds if b['tipo'] == 'LTN'],   key=lambda x: x['vencimento'])
    ntnfs = sorted([b for b in bonds if b['tipo'] == 'NTN-F'], key=lambda x: x['vencimento'])

    known_dates = {b['vencimento'] for b in ltns}

    selected_ntnfs = []
    for ntnf in ntnfs:
        if ntnf['vencimento'] in known_dates:
            continue

        flows        = generate_cash_flows(ntnf, base_date)
        coupon_dates = set(flows.keys()) - {ntnf['vencimento']}

        if not coupon_dates:
            continue

        if coupon_dates.issubset(known_dates):
            selected_ntnfs.append(ntnf)
            known_dates.add(ntnf['vencimento'])

    return ltns + selected_ntnfs

# ------------------------------------------------------------
# PARTE 5: CONSTRUÇÃO DO SISTEMA LINEAR  Cd = P
# ------------------------------------------------------------

def build_system(bonds: List[Dict], base_date: datetime.date, holidays: Set[datetime.date]):
    """
    Monta a matriz C (fluxos de caixa) e o vetor P (preços de mercado).
    Retorna (C, P, payment_dates).
    """
    bonds = filter_triangular_bonds(bonds, base_date)

    bond_flows = []
    for bond in bonds:
        flows = generate_cash_flows(bond, base_date)
        flows = {dt: val for dt, val in flows.items() if dt > base_date}
        bond_flows.append({
            'vencimento': bond['vencimento'],
            'flows':      flows,
            'pu':         bond['pu'],
        })

    bond_flows.sort(key=lambda x: x['vencimento'])

    payment_dates = sorted({dt for bf in bond_flows for dt in bf['flows']})

    C, P = [], []
    for bf in bond_flows:
        C.append([bf['flows'].get(dt, 0.0) for dt in payment_dates])
        P.append(bf['pu'])

    return C, P, payment_dates

# ------------------------------------------------------------
# PARTE 6: RESOLUÇÃO — SUBSTITUIÇÃO PROGRESSIVA (FORWARD SUBSTITUTION)
# ------------------------------------------------------------

def forward_substitution(C: List[List[float]], P: List[float]) -> List[float]:
    """
    Resolve Cd = P para matriz triangular inferior C.
    Complexidade: O(n²).
    """
    n = len(P)
    d = [0.0] * n
    for i in range(n):
        soma = sum(C[i][j] * d[j] for j in range(i))
        if abs(C[i][i]) < 1e-12:
            raise ZeroDivisionError(f"Elemento diagonal nulo na linha {i} — sistema singular.")
        d[i] = (P[i] - soma) / C[i][i]
    return d

# ------------------------------------------------------------
# PARTE 7: CURVA SPOT
# ------------------------------------------------------------

def compute_spot_curve(
    d: List[float],
    payment_dates: List[datetime.date],
    base_date: datetime.date,
    holidays: Set[datetime.date],
) -> List[Dict]:
    """Converte fatores de desconto em taxas spot anuais (base 252 DU)."""
    curva = []
    for i, dt in enumerate(payment_dates):
        du         = count_business_days(base_date, dt, holidays)
        prazo_anos = du / 252.0
        fator      = d[i]
        taxa_spot  = (1.0 / fator) ** (1.0 / prazo_anos) - 1.0 if prazo_anos > 0 else 0.0
        curva.append({
            "data":           dt.isoformat(),
            "du":             du,
            "prazo_anos":     round(prazo_anos, 6),
            "fator_desconto": round(fator,      8),
            "taxa_spot":      round(taxa_spot,  6),
        })
    return curva

# ------------------------------------------------------------
# PARTE 8: VALIDAÇÃO — RE-PRECIFICAÇÃO
# ------------------------------------------------------------

def repricing_error(C: List[List[float]], d: List[float], P: List[float]) -> float:
    """Retorna o erro máximo absoluto de re-precificação (deve ser ~0)."""
    return max(
        abs(sum(C[i][j] * d[j] for j in range(len(d))) - P[i])
        for i in range(len(P))
    )

# ------------------------------------------------------------
# PARTE 9: INTERFACE PÚBLICA
# ------------------------------------------------------------

def bootstrap(bonds_file: str, holidays_file: str) -> Dict:
    """
    Constrói a curva zero-cupom a partir dos arquivos da ANBIMA.

    Parâmetros
    ----------
    bonds_file    : caminho para o TXT de preços da ANBIMA
    holidays_file : caminho para o arquivo de feriados (.xls, .csv ou .txt)

    Retorna
    -------
    dict com data_base, erro_reprecificacao e lista de vértices da curva
    """
    holidays              = load_holidays(holidays_file)
    base_date, bonds      = parse_bonds(bonds_file)
    C, P, payment_dates   = build_system(bonds, base_date, holidays)

    n_bonds, n_dates = len(P), len(payment_dates)
    if n_bonds != n_dates:
        raise ValueError(
            f"Sistema não quadrado após filtragem: {n_bonds} títulos × {n_dates} datas. "
            f"Verifique se os vencimentos das LTNs cobrem os cupons das NTN-Fs selecionadas."
        )
    for i in range(n_bonds):
        if abs(C[i][i]) < 1e-12:
            raise ValueError(
                f"Diagonal nula na linha {i} (data {payment_dates[i].isoformat()}). "
                f"O filtro deixou passar um título incompatível com a estrutura triangular."
            )

    d     = forward_substitution(C, P)
    curva = compute_spot_curve(d, payment_dates, base_date, holidays)
    error = repricing_error(C, d, P)

    return {
        "data_base":            base_date.isoformat(),
        "erro_reprecificacao":  error,
        "curva":                curva,
    }


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python bootstrapping.py <titulos.txt> <feriados.xls|csv|txt>")
        sys.exit(1)
    try:
        result = bootstrap(sys.argv[1], sys.argv[2])
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"ERRO: {e}", file=sys.stderr)
        sys.exit(1)