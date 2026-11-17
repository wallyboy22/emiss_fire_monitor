# Tradução pt-BR → inglês

Cole este texto junto com o arquivo `traducoes_pt_en.csv` na IA que vai traduzir.

---

Preencha a coluna `en` do CSV anexo com a tradução para o inglês da coluna `pt`. É a interface de um painel científico sobre emissões de gases de efeito estufa por queimadas no Brasil (dados do MapBiomas Fogo, estimativa do IPAM).

Regras:

1. Devolva o mesmo CSV, com as mesmas colunas, linhas e ids, na mesma ordem. Altere só a coluna `en`.
2. Não altere as linhas que já têm `en` preenchido (nomes oficiais do MapBiomas).
3. Muitas linhas são pedaços de frases que o código monta, como `' foi o bioma que mais emitiu'` ou `' t CO₂e, contra '`. Mantenha os espaços do início e do fim exatamente como estão, e também a pontuação das pontas. Use a coluna `contexto` (o trecho de código ou a tag HTML de onde o texto saiu) para entender onde o pedaço entra. Se a ordem das palavras em inglês exigir outra montagem da frase, traduza o pedaço do melhor jeito possível e escreva `[REVISAR]` no fim da tradução.
4. Não traduza: siglas de estados (PA, AM…), nomes de estados, nomes próprios (MapBiomas, IPAM, SEEG, GFED, IPCC), fórmulas químicas (CO₂, CH₄, N₂O, CO₂e), unidades (ha, t, t/ha) e símbolos (Σ, ÷, ×, ·).
5. Use o inglês dos EUA, com tom técnico e direto, e frases curtas como no original.
6. Números e datas dentro do texto ficam iguais. A formatação numérica é feita pelo código.
7. Use sempre os mesmos termos:

| pt | en |
|---|---|
| Área queimada | Burned area |
| Emissão / emissões | Emissions |
| Por ha queimado | Per burned hectare |
| Por ha de território | Per hectare of territory |
| Recorte | Selection |
| Destaques do mês | Monthly highlights |
| Painel | Dashboard |
| Método | Methods |
| Vegetação nativa | Native vegetation |
| Agropecuária | Farming |
| Nativa × agro | Native vs. farming |
| Cobertura (do solo) | Land cover |
| Bioma | Biome |
| UF / estado | State |
| Região | Region |
| Acumulado do ano | Year to date |
| Matéria seca | Dry matter |
| Fator de combustão | Combustion factor |
| Fator de emissão | Emission factor |
| Estoque de carbono | Carbon stock |
| Biomassa aérea | Aboveground biomass |
| Madeira morta | Dead wood |
| Serrapilheira | Litter |
| Página não oficial e exploratória | Unofficial, exploratory page |
| mil / milhões / bilhões | thousand / million / billion |
