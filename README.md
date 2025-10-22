"old" contains the original interpreter which was mostly built before the introduction of arrays.
"main" contains the new interpreter, with the file "psmain.py" being the main file. The value of "CODE_PATH" specifies where to read code from. If blank: it will read from the builtin sample program.
Input operations begrudgingly do NOT parse more than one variable per user input query, the programmer is expected to query individual variables separately or manually parse results using builtin slicing & string searching operations.
