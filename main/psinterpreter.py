from pstyper import Type, Any, Basic, List, Procedure, Function, ListFunction, SIMPLE_TYPES
import json

BUILTINS = {
    "isNumeric": str.isnumeric,
    "isWhitespace": str.isspace,
    "isUpper": str.isupper,
    "isChar": (lambda s: len(s) == 1),
    "isLower": str.islower,
    "toString": str,
    "toNumber": int,
    "length": len,
    "find": str.index,
    "getFirst": (lambda s, x: s[:x]),
    "getLast": (lambda s, x: s[x:]),
    "getBetween": (lambda s, x, y: s[x:y]),
}

def accept_number_input(print_function, input_function, support_float) -> int|float:
    # TODO: review
    attempts = 3
    while attempts > 0:
        attempts -= 1
        try:
            user_input = input_function()
            if "." not in user_input:
                return int(user_input)
            elif support_float:
                return float(user_input)
            else:
                raise ValueError("floating point numbers are disabled for this program")
        except ValueError as e:
            print_function(e, "- please try again")
    print_function("using input=0")
    return 0

class Variable:
    def __init__(self, type: Type, value=None):
        if not isinstance(type, Type):
            raise TypeError(type)
        self.type = type
        self.value = value

class Interpreter:
    @staticmethod
    def function_prefix(op: str, right):
        match op:
            case "NOT":
                return not right
            case "-":
                return -right
            case x:
                raise NotImplementedError(f"prefix '{x}' not implemented")
    @staticmethod
    def function_infix(op: str, left, right):
        if op in ("<=", ">=") and left == right:
            return True
        if op in ("<=", "<"):
            return left < right
        if op in (">=", ">"):
            return left > right
        if op in ("=", "<>"):
            return (left == right) == (op == "=")
        match op:
            case "+":
                return left+right
            case "-":
                return left-right
            case "*":
                return left*right
            case "/":
                if isinstance(left, float) or isinstance(right, float):
                    return left/right
                return left//right
            case "%":
                return left%right
            case x:
                raise NotImplementedError(f"infix '{x}' not implemented")
    #
    support_float = False
    @classmethod
    def canonical_input(cls) -> str:
        return input()
    @classmethod
    def canonical_print(cls, *args):
        print(*args)
    def __init__(self, parse_tree):
        self.open_files = {}
        self.main_body = parse_tree["starts"][0]["body"]
        self.procedures = dict((i["name"], i) for i in parse_tree["procedures"])
        self.var_stack = [{"eof": Variable(Basic("bool"), False)}]
    def start(self):
        self.read_declarations(self.main_body["declarations"])
        try:
            for stmt in self.main_body["statements"]:
                self.do_statement(stmt)
        except Exception as e:
            for file in self.open_files.values():
                file.close()
            raise e
    def read_declarations(self, decls):
        for dec in decls:
            pred = dec["predicate"]
            var_name = pred["name"]
            var_type = self.build_type(pred)
            initial_value = dec.get("initial")
            if initial_value is None:
                initial_value = var_type.get_garbage()
            else:
                initial_value = self.eval_expr(initial_value)
            self.var_stack[-1][var_name] = Variable(var_type, initial_value)
    def build_type(self, pred) -> Type:
        raw_element, raw_suffixes = pred["element"], pred["suffixes"]
        element = self.decide_type(raw_element)
        for suff in raw_suffixes:
            element = self.decide_suffixed(element, suff)
        return element
    def decide_type(self, elem) -> Type:
        if elem["type"] in SIMPLE_TYPES:
            return Basic(elem["type"])
        raise NotImplementedError(f"type-elements {repr(elem['type'])}")
    def decide_suffixed(self, elem, suff) -> Type:
        match suff["type"]:
            case "array":
                size = suff["size"]
                if size is None:
                    return List(elem)
                value = self.eval_expr(size)
                return List(elem, value)
            case x:
                raise NotImplementedError(f"type-suffix {repr(x)}")
        raise NotImplementedError # TODO
    def select_open_mode(self, name: str):
        var = self.get_var(name)
        if var.type == Basic("InputFile"):
            return "r"
        if var.type == Basic("OutputFile"):
            return "w"
        raise TypeError("unsupported file type", var.type)
    def do_statement(self, stmt):
        if stmt is None: return
        match stmt["type"]:
            case "body":
                self.do_body(stmt)
            case "if":
                self.do_if(stmt)
            case "while":
                self.do_while(stmt)
            case "do":
                self.do_do_until(stmt)
            case "for":
                self.do_for_step(stmt)
            case "case":
                self.do_case(stmt)
            case "set":
                self.do_set(stmt)
            case "input":
                self.do_input(stmt)
            case "output":
                self.do_output(stmt)
            case "open":
                mode = self.select_open_mode(stmt["name"])
                self.do_open(stmt, mode)
            case "close":
                self.do_close(stmt)
            case "exprstmt":
                # procedures return _void_ which can only appear here, where types aren't checked
                # _void_ is incompatible with all types, including itself, like float('Nan')
                self.eval_expr(stmt["value"])
            case x:
                raise NotImplementedError(f"statement type '{x}'")
    # statements
    def do_body(self, stmt):
        for sub in stmt["statements"]:
            self.do_statement(sub)
    def do_if(self, stmt):
        branch = stmt["else"]
        condition = self.eval_expr(stmt["condition"])
        if condition:
            branch = stmt["body"]
        self.do_statement(branch)
    def do_while(self, stmt):
        while self.eval_expr(stmt["condition"]):
            self.do_statement(stmt["body"])
    def do_do_until(self, stmt):
        while True:
            self.do_statement(stmt["body"])
            if self.eval_expr(stmt["condition"]):
                break
    def do_for_step(self, stmt):
        start_expr, stop_expr, step_expr = stmt["range"]
        start_val = self.eval_expr(start_expr)
        stop_val = self.eval_expr(stop_expr)
        step_val = self.eval_expr(step_expr)
        var_name = stmt["variable"]
        if step_val == 0:
            raise ZeroDivisionError("step value cannot be zero")
        if (start_val == stop_val) or (start_val < stop_val) != (0 < step_val):
            return # empty range
        negative = step_val < 0
        if negative: # ensure the loop condition comparison works as expected
            step_val, start_val, stop_val = -step_val, -start_val, -stop_val
        index = 0
        parameter = start_val
        current_local = self.var_stack[-1]
        # why go through all this trouble?
        # python doesn't support float ranges;
        # this is the most stable and error-resistant way to implement them
        while parameter < stop_val:
            if negative:
                parameter = -parameter
            current_local[var_name] = Variable(Basic("num"), parameter)
            self.do_body(stmt["body"])
            index += 1
            parameter = start_val + step_val * index
        # in case the loop never triggered for any reason, check
        if var_name in current_local:
            del current_local[var_name]
    def do_case(self, stmt):
        arg_value = self.eval_expr(stmt["variable"])
        chosen_body = stmt["default"]
        for case in stmt["cases"]:
            case_test = self.eval_expr(case["test"])
            if case_test == arg_value:
                chosen_body = case["body"]
                break
        self.do_statement(chosen_body)
    def do_set(self, stmt):
        new_value = self.eval_expr(stmt["expr"])
        self.assign_to_lval(stmt["lval"], new_value)
    def do_input(self, stmt):
        variables = []
        seen = set()
        for name in stmt["values"]:
            if name in seen:
                raise NameError("cannot assign to the same variable multiple times in the same input statement")
            variables.append(self.get_var(name))
            seen.add(name)
        # read input
        destination = stmt["file"]
        if destination is None:
            results = self.probe_console_input(variables)
            for v,r in zip(variables, results):
                v.value = r
            return
        file = self.eval_atom(destination)
        string = file.readline()
        if not string:
            self.get_var("eof").value = True
            return
        if string[-1] == "\n":
            string = string[:-1]
        results = json.loads("["+string+"]")
        for v,r in zip(variables, results):
            if v.type == Basic("num"):
                v.value = int(r)
            elif v.type == Basic("float"):
                v.value = float(r)
            elif v.type == Basic("string"):
                v.value = r
            else:
                raise NotImplementedError("undefined input type")
    def probe_console_input(self, variables):
        if len(variables) != 1:
            raise NotImplementedError # TODO: take input and parse it out to a list of variables
        only_var = variables[0]
        results = []
        if only_var.type == Basic("num"):
            results.append(accept_number_input(self.canonical_print, self.canonical_input, False))
        elif only_var.type == Basic("float"):
            results.append(float(accept_number_input(self.canonical_print, self.canonical_input, True)))
        elif only_var.type == Basic("string"):
            results.append(input())
        else:
            raise NotImplementedError("undefined input type")
        return results
    def get_var(self, name) -> Variable | None:
        for vars in reversed(self.var_stack):
            if name in vars:
                return vars[name]
        raise NameError(f"writing to undeclared variable {repr(name)}")
    def do_output(self, stmt):
        parts = []
        for part in stmt["values"]:
            parts.append(self.eval_expr(part))
        destination = stmt["file"]
        if destination is None:
            self.canonical_print(*parts) # assume type check has validated this
        else:
            file = self.eval_atom(destination)
            file.write(", ".join(repr(i) for i in parts)+"\n")
    def do_open(self, stmt, mode):
        path = self.eval_atom(stmt["path"])
        if path in self.open_files:
            raise PermissionError("...")
        var = self.get_var(stmt["name"])
        file = open(path, mode)
        var.value = file
        self.open_files[path] = file
    def do_close(self, stmt):
        file = self.get_var(stmt["name"]).value
        key = None
        for k,v in self.open_files.items():
            if v == file:
                key = k
                break
        file.close()
        if key is None:
            raise ValueError("actual file does not correspond to any previously opened path")
        del self.open_files[key]
    def read_var(self, name):
        if name in BUILTINS:
            return BUILTINS[name]
        for vars in reversed(self.var_stack):
            if name in vars:
                result = vars[name].value
                if result is None:
                    raise NameError(f"{repr(name)} read before assignment")
                return result
        if name in self.procedures:
            return self.procedures[name]
        raise NameError(f"{repr(name)} referenced before declaration- how did this escape the typechecker?")
    # special
    def assign_to_lval(self, lval, value):
        match lval["type"]:
            case "variable":
                name = lval["name"]
                if name in BUILTINS:
                    raise TypeError(f"cannot assign to builtin constant {name}")
                for vars in reversed(self.var_stack):
                    if name in vars:
                        vars[name].value = value
                        return
            case "subscript":
                head = self.eval_term(lval["head"])
                index = self.eval_expr(lval["index"])
                head[index] = value
            case x:
                raise NotImplementedError(f"lval type {repr(x)}")
    # expressions
    def eval_expr(self, expr):
        # TODO: maybe break apart recursive expr calls into a stack accumulation
        match expr["type"]:
            case "infix":
                op = expr["operator"]
                left = self.eval_expr(expr["left"])
                if op in ("AND", "OR") and (left == (op == "OR")):
                    return left
                right = self.eval_expr(expr["right"])
                if op in ("AND", "OR"):
                    return right
                return self.function_infix(op, left, right)
            case "prefix":
                op = expr["operator"]
                right = self.eval_expr(expr["right"])
                return self.function_prefix(op, right)
            case _:
                return self.eval_term(expr)
    def eval_expr_iterative(self, expr):
        # ok it turns out this looks a lot more complicated than the simple recursive calls above
        # a python-style bytecode compilation (so- no recursion required) would be a nice long-term goal
        # UNTESTED
        todo = [expr]
        buffer = []
        while todo:
            first = todo[0]
            match first["type"]:
                case "infix":
                    if first["operator"] not in ("AND", "OR"):
                        todo[0:1] = [first["left"], first["right"], {"type": "buffer-infix", "op":first["operator"]}]
                    else:
                        todo[0:1] = [first["left"], {"type": "lazy-infix", "op":first["operator"], "right":first["right"]}]
                case "prefix":
                    todo[0:1] = [first["right"], {"type": "buffer-prefix", "op":first["operator"]}]
                case "buffer-prefix":
                    todo.pop(0)
                    buffer[-1] = self.function_prefix(first["op"], buffer[-1])
                case "lazy-infix":
                    if buffer[-1] == (first["op"] == "OR"):
                        # true OR x -> true; false AND x -> false
                        todo.pop(0)
                    else:
                        # false OR x -> x; true AND x -> x
                        buffer.pop(-1)
                        todo[0:1] = [first["right"]]
                case "buffer-infix":
                    todo.pop(0)
                    right = buffer.pop(-1)
                    buffer[-1] = self.function_infix(first["op"], buffer[-1], right)
                case _:
                    buffer.append(self.eval_term(todo.pop(0)))
        if len(buffer) != 1:
            raise RuntimeError("badly structured data in expression evaluation")
        return buffer[0]
    def eval_term(self, term):
        suffixes = []
        while term["type"] == "term":
            suffixes.append(term["suffix"])
            term = term["head"]
        head = self.eval_atom(term)
        for suff in reversed(suffixes):
            head = self.apply_suffix(head, suff)
        return head
    def eval_atom(self, atom):
        match atom["type"]:
            case "num" | "float" | "string" | "bool":
                return atom["value"]
            case "name":
                name = atom["value"]
                return self.read_var(name)
            case "group":
                return self.eval_expr(atom["value"])
            case "list":
                elements = []
                for e in atom["value"]:
                    elements.append(self.eval_expr(e))
                return elements
            case x:
                raise NotImplementedError(f"atom type {repr(x)}")
    def apply_suffix(self, head, suff):
        match suff["type"]:
            case "subscript": # x[y]
                index = self.eval_expr(suff["value"])
                return head[index]
            case "call": # x(y...)
                args = []
                for arg in suff["value"]:
                    args.append(self.eval_expr(arg))
                if isinstance(head, dict):
                    return self.call_function(head, args)
                return head(*args)
            case x:
                raise NotImplementedError(f"suffix type {repr(x)}")
    def call_function(self, code, args):
        new_local = {}
        for pair, arg in zip(code["args"], args):
            t = self.build_type(pair)
            new_local[pair["name"]] = Variable(t, arg)
        self.var_stack.append(new_local)
        self.read_declarations(code["body"]["declarations"])
        self.do_body(code["body"])
        self.var_stack.pop(-1)
