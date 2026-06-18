# Bootstrap de Curva Zero-Cupom (Tesouro Direto)

Solução para o desafio de bootstrapping de títulos públicos prefixados (LTN e NTN-F), conforme especificação da ANBIMA.

## (a) Modelagem do Problema

O preço de um título é a soma de seus fluxos futuros descontados por fatores de desconto di:

P = Σ VFi * di

Para um conjunto de títulos com vencimentos em n datas distintas, construímos:
- **C** ∈ R^(m×n): matriz de fluxos de caixa, onde C[j][i] é o valor pago pelo título j na data i.
- **P** ∈ R^m: vetor de preços de mercado (PU).
- **d** ∈ R^n: vetor de fatores de desconto (incógnitas).

O sistema a ser resolvido é: **C · d = P**.

Para títulos LTN (zero-cupom) e NTN-F (com cupons semestrais de 10% a.a.), a matriz C é triangular inferior quando ordenamos os títulos por vencimento crescente, permitindo resolução sequencial.

Os dias úteis são contados com base no calendário da ANBIMA (excluindo fins de semana e feriados), e a convenção de ano é de 252 dias úteis.

A taxa spot anual é recuperada por: s_i = d_i^(-1/prazo_anos) - 1.

## (b) Método de Resolução e Justificativa

Escolhi a **substituição progressiva (forward substitution)** para resolver o sistema linear triangular inferior.

**Justificativa:**
1. O enunciado (Seção 2.4) explicitamente orienta a explorar a estrutura triangular inferior da matriz C.
2. É o método mais estável numericamente para este caso, pois não envolve inversão de matrizes ou eliminação gaussiana completa.
3. É extremamente eficiente: cada fator de desconto é calculado diretamente a partir do título de vencimento mais curto, usando os fatores já resolvidos para os vértices anteriores.
4. Atende ao requisito de não usar bibliotecas prontas de bootstrapping, utilizando apenas numpy para operações básicas.

## (c) Complexidade da Solução

- **Tempo:** O(n²), onde n é o número de vértices (datas de pagamento). Isso porque, para cada título i, iteramos sobre todos os fluxos anteriores j < i.
- **Espaço:** O(n²) para armazenar a matriz de fluxos, ou O(n) se otimizado para armazenar apenas a diagonal e os fluxos passados. No código, usei uma abordagem direta com matriz O(n²) por clareza, já que n é pequeno (títulos do Tesouro Direto).

## Validação (R5)

A solução re-precifica cada título de entrada usando a curva gerada. O erro absoluto máximo é inferior a 1×10⁻⁴, conforme exigido.

## Como executar

```bash
# Instale as dependências
pip install numpy pytest

# Execute o bootstrap
python main.py  # (ou o nome do seu script principal)

# Rode os testes automatizados
pytest test_bootstrap.py -v
