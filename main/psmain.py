from psparser import Parser, Postparser
from pstyper import TypeChecker, Type
from code_samples import sample, old_sample, test_sample, test_output, test_input
from psinterpreter import Interpreter

# location of input code
CODE_PATH = ""
# destinations to debug various intermediate steps
RAW_DESTINATION = ""
TREE_DESTINATION = ""
TYPE_DESTINATION = ""

def maybe_store(path, content):
    if path:
        with open(path, "w") as file:
            file.write(str(content))

def interpret(path: str=None, code: str=None):
    if path is not None:
        with open(path, "r") as file:
            code = file.read()
    if code is None:
        quit()
    ok, _, raw_tree = Parser.parse(code)
    if not ok:
        print("Parse failed")
        quit()
    maybe_store(RAW_DESTINATION, raw_tree)
    tree = Postparser(0).p_file(raw_tree)
    maybe_store(TREE_DESTINATION, tree)
    try:
        types = TypeChecker.check_file(tree)
    except Exception as e:
        print(e)
        print("Type Check failed")
        quit()
    maybe_store(TYPE_DESTINATION, types)
    Interpreter(tree).start()

if __name__ == "__main__":
    if CODE_PATH:
        interpret(path=CODE_PATH)
    else:
        interpret(code=sample)

