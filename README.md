# Bootstrapping da Curva Zero-Cupom

## Como executar

    pip install xlrd pytest
    python bootstrapping.py <titulos.txt> <feriados.xls|csv|txt>
    pytest test_bootstrap.py -v

## (a) Modelagem

O preço de um título é a soma dos seus fluxos futuros descontados pelas taxas spot de cada vencimento:

    P = soma(VF_i * d_i)

Organizando m títulos e n datas de pagamento, isso vira o sistema linear C * d = P, onde C é
a matriz de fluxos de caixa, d o vetor de fatores de desconto (incógnitas) e P o vetor de preços.

A chave é ordenar os títulos por vencimento e garantir que cada um adicione exatamente uma
data nova. LTNs são zero-cupom (só pagam no vencimento). NTN-Fs só entram no sistema se todos
os seus cupons futuros já caírem em datas cobertas por títulos anteriores. Com isso, C fica
quadrada e triangular inferior — o que permite uma resolução mais eficiente.

Convenção brasileira: prazo em dias úteis (DU), base 252. Feriados lidos do arquivo da ANBIMA
(.xls, .csv ou .txt).

## (b) Método de resolução

Com C triangular inferior, o sistema é resolvido por substituição progressiva (forward substitution):

    d_i = (P_i - soma_{j<i} C_ij * d_j) / C_ii

Cada fator de desconto depende apenas dos anteriores, já calculados. Não é necessário inverter
a matriz nem aplicar eliminação gaussiana completa, a estrutura triangular é explorada diretamente.

## (c) Complexidade

A etapa dominante é a substituição progressiva: O(n²), onde n é o número de vértices da curva.
A construção da matriz C também é O(n²). A curva pré-fixada da ANBIMA tem tipicamente entre
10 e 20 vértices, então n é pequeno na prática e Python puro é suficiente.

## Estrutura

    bootstrapping.py   solução principal
    test_bootstrap.py  testes automatizados (pytest)
    README.md

## Dependências

    Python 3.10+
    xlrd   (pip install xlrd)   — leitura do .xls de feriados
    pytest (pip install pytest) — execução dos testes
