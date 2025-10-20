from psparser import Parser, Postparser
from pstyper import TypeChecker, Type
from code_samples import sample, old_sample, test_sample, test_output, test_input
from psinterpreter import Interpreter

if __name__ == "__main__":
    ok, index, result = Parser.parse(test_input)
    if not ok:
        print("Parse failed")
        quit()
    new_result = Postparser(0).p_file(result)
    print(new_result)
    try:
        TypeChecker.check_file(new_result)
    except Exception as e:
        print(e)
        print("Type Check failed")
        quit()
    Interpreter(new_result).start()
