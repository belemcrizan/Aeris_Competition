# Semantic localization

search_similar_code(query, k) returns the k repository graph nodes whose precomputed embeddings are most similar to the query. Node ids are fully qualified Python symbols such as package.module.Class.method.

- Use it right after understanding the issue, before broad grep. Write the query as a short description of the faulty behavior plus key identifiers, for example: "serialize response model exclude unset fields". Do not paste the entire issue.
- Use k between 8 and 12. Run at most three distinct queries per task, each worded differently. Never repeat a query.
- Results are candidates, not conclusions: embedding similarity does not show causation. Confirm candidates by reading their source.
- Combine with grep: symbols that appear both in search results and in grep hits for identifiers from the issue are the strongest candidates.
- To turn node ids into file paths and line numbers, run the navigation skill script locate_symbol.py with the node ids as arguments. To find the tests that exercise a file or symbol, run find_tests.py from the same skill with the file paths or symbol names.
