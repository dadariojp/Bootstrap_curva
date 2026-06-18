# Bootstrap da Curva Zero-Cupom (Tesouro Direto)

Solução completa para o desafio de bootstrapping de títulos públicos prefixados (LTN e NTN-F), conforme especificação da ANBIMA.

---

## Visão Geral

O programa lê os arquivos de preços (formato ANBIMA) e de feriados, constrói a **curva de juros zero-cupom** a partir dos PUs de mercado e retorna os fatores de desconto e taxas spot anuais para cada vértice (data de pagamento).

A implementação respeita as convenções brasileiras:
- Base de dias úteis: 252
- Contagem de dias úteis excluindo fins de semana e feriados
- LTN: zero-cupom, paga R$ 1.000 no vencimento
- NTN-F: cupom semestral de 10% a.a. (R$ 48,8088 por cupom) + principal R$ 1.000

---

## Modelagem do Problema (a)

O preço de um título é a soma de seus fluxos futuros descontados:

$$
P_j = \sum_{i=1}^{n} C_{j,i} \cdot d_i
$$

- $C_{j,i}$ é o fluxo de caixa (valor futuro) do título $j$ no vértice $i$
- $d_i$ é o fator de desconto do vértice $i$ (incógnita)

Para um conjunto de $m$ títulos com pagamentos em $n$ datas distintas, o sistema linear é:

$$
C \cdot d = P
$$

Aqui:
- \( C \) é a matriz de fluxos (m × n)
- \( d \) é o vetor de fatores de desconto (n × 1)
- \( P \) é o vetor de preços de mercado (m × 1)

A estrutura do problema é explorada para garantir que \( C \) seja **triangular inferior**, permitindo resolução por substituição progressiva.

---

## Método de Resolução (b)

### Escolha do método: **substituição progressiva (forward substitution)**

**Justificativa:**
1. O enunciado (Seção 2.4) orienta a explorar a estrutura triangular inferior da matriz C.
2. O método é **estável numericamente** não exige inversão de matrizes, fatoração LU ou eliminação de Gauss.
3. É **eficiente**: cada fator de desconto é calculado diretamente a partir do título de vencimento mais curto, usando os fatores já resolvidos para os vértices anteriores.
4. Atende ao requisito de não usar bibliotecas prontas de bootstrapping, foi utilizado apenas `numpy` (para operações básicas) e bibliotecas padrão.

### Estratégia de filtragem dos títulos

Para obter a matriz triangular, o código implementa uma função `filter_triangular_bonds()` que:

- Seleciona **todas as LTNs** (pois são zero-cupom e cada uma contribui com uma única data).
- Para cada NTN-F, verifica se:
  - Seu vencimento **não** coincide com outra data já conhecida.
  - Possui **pelo menos um cupom futuro** (não é zero-cupom).
  - **Todos os seus cupons futuros** já estão presentes no conjunto de datas conhecidas (garantia de triangularidade).

Isso assegura que a matriz C seja **quadrada e triangular inferior** sem necessidade de interpolação ou ajustes artificiais.

---

## Complexidade da Solução (c)

- **Tempo:** \( O(n^2) \), onde \( n \) é o número de vértices (datas de pagamento). Para cada título \( i \), percorremos todos os fluxos anteriores \( j < i \).
- **Espaço:** \( O(n^2) \) para armazenar a matriz C (por simplicidade, pois \( n \) é pequeno, tipicamente < 50 títulos). Pode ser otimizada para \( O(n) \) com armazenamento esparso, mas optamos pela clareza.

---

## Como Executar

### Dependências

- Python 3.8+ (ou 3.10+ para a sintaxe de type hints com `|`, mas o código usa `Optional` para compatibilidade)
- Bibliotecas: `xlrd` (para ler arquivos .xls de feriados)

Instale a dependência:

```
pip install xlrd
```

### Comando

```bash
python bootstrap.py <caminho_para_titulos.txt> <caminho_para_feriados.xls|csv|txt>
```
###Exemplo

```bash:

python bootstrap.py exemplo_anbima.txt feriados_nacionais.xls
```

###Saída
A função imprime um JSON com:

json
{
  "data_base": "2026-06-01",
  "erro_reprecificacao": 0.0,
  "curva": [
    {
      "data": "2026-07-01",
      "du": 21,
      "prazo_anos": 0.083333,
      "fator_desconto": 0.988866,
      "taxa_spot": 0.143798
    },
    ...
  ]
}


---

## Validação (R5)

Após a resolução, o código recalcula (re-precifica) **cada título de entrada** usando os fatores de desconto obtidos.

O erro máximo absoluto entre o preço original e o recalculado é calculado na função `repricing_error()`. O valor deve ser **inferior a $10^{-4}$**, conforme exigido.

Para executar o teste automatizado:

```bash
pytest test_bootstrap.py -v
```


**Status:** Todos os testes passam (erro de re-precificação < $10^{-4}$).

---

## Estrutura do Código

- `parse_*` – Leitura dos arquivos da ANBIMA e feriados
- `generate_cash_flows` – Geração dos fluxos para LTN e NTN-F
- `filter_triangular_bonds` – Seleção inteligente de títulos para garantir matriz triangular
- `build_system` – Montagem da matriz $C$ e vetor $P$
- `forward_substitution` – Resolução do sistema triangular
- `compute_spot_curve` – Cálculo das taxas spot a partir dos fatores de desconto
- `repricing_error` – Validação da re-precificação
- `bootstrap` – Função principal que orquestra todo o processo

---

## Observações finais

- O código foi desenvolvido seguindo as convenções de mercado brasileiro e as orientações do desafio.
- A escolha por **não usar bibliotecas de bootstrapping** prontas garante total transparência e controle sobre o método.
- A solução é **modular** e facilmente adaptável para novos tipos de títulos ou calendários de feriados.

---

**Autor:** João Pedro Dadario Pereira
**Data:** Junho/2026