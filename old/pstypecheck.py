
POSSIBLE_LITERALS = ("bool", "num", "string")
INFIX_TYPE_MAP = dict(
    [(op, {("bool", "bool"): "bool"}) for op in ["OR", "AND"]]+
    [(op, {("num", "num"): "num"}) for op in "- * / %".split()]+
    [("+", {("num", "num"): "num", ("string", "string"): "string"})]+
    [(op, {("num", "num"): "bool", ("string", "string"): "bool"}) for op in "< > <= >=".split()]+
    [(op, dict(((i,i),"bool") for i in "bool num string proc".split())) for op in "= <>".split()])
# <> and = are XOR and XNOR respectively, over the booleans
PREFIX_TYPE_MAP = {
    "NOT": {"bool": "bool"},
    "-": {"num": "num"},
}
BUILTIN_TYPES = dict((name, {("string",):"bool"}) for name in "isNumeric isChar isWhitespace isUpper isLower".split())
BUILTIN_TYPES["length"] = {("string",):"num"}
BUILTIN_TYPES["find"] = {("string", "string"):"num"}
BUILTIN_TYPES["slice"] = {("string", "num"):"string", ("string", "num", "num"):"string"}
BUILTIN_TYPES["toString"] = {("num",):"string"}
BUILTIN_TYPES["toNumber"] = {("string",):"num"}
LIST_MORPHIC = {"length": {(1,):"num"}, "slice": {(1, "num"):1, (1, "num", "num"):1}}

class TypeChecker:
    @classmethod
    def check_program(cls, tree) -> None|tuple[dict[str,str], dict[str,dict[str,str]]]:
        start = None
        procedures = []
        for i in tree:
            if i["type"] != "start":
                procedures.append(i)
            elif start is None:
                start = i
            else:
                print("only one start is allowed per program")
                return
        if start is None:
            print("a start is required per program")
            return
        procedure_names = []
        for proc in procedures:
            nam = proc["name"]
            if nam in procedure_names:
                print(f"duplicate procedure defined with name {nam}")
                return
            procedure_names.append(nam)
        pnameset = set(procedure_names)
        ok, global_variables = cls.gather_declarations((), pnameset, start["declarations"], "duplicate global variable declared")
        if not ok:
            return
        procedure_types = {}
        def layer(x, y):
            for _ in range(y):
                x = [x]
            return x
        for pname, proc in zip(procedure_names, procedures):
            procedure_types[pname] = tuple(layer(i["type"], i["depth"]) for i in proc["arguments"])
        if not cls(procedure_types, global_variables, {}).check_body(start["declarations"], start["statements"], "main statement type check failed"):
            return
        local_records = {}
        for pname, proc in zip(procedure_names, procedures):
            ok, local_variables = cls.gather_declarations(tuple((i["name"], layer(i["type"], i["depth"])) for i in proc["arguments"]), pnameset, proc["declarations"], f"duplicate local variable declared in procedure {proc['name']}")
            local_records[pname] = local_variables
            if not ok:
                return
        for pname, proc in zip(procedure_names, procedures):
            if not cls(procedure_types, global_variables, local_records[pname]).check_body(proc["declarations"], proc["statements"], f"procedure statement type check failed in procedure {proc['name']}"):
                return
        return (global_variables, local_records)
    @classmethod
    def gather_declarations(cls, arguments, exclude, decls, message) -> tuple[bool, dict]:
        type_map = {}
        argnameset = set()
        for name, typ in arguments:
            if name in type_map:
                print("duplicate named arugment detected {arguments}")
                return (False, type_map)
            type_map[name] = typ
            argnameset.add(name)
        for dec in decls:
            typ = dec["type"]
            for _ in range(dec["depth"]):
                typ = [typ]
            nam = dec["name"]
            if nam in exclude:
                print("cannot overshadow the names of global procedures")
                return (False, type_map)
            if nam in argnameset:
                print("input variables are declared in the () header, not the Declarations section")
                return (False, type_map)
            if nam in type_map:
                print(message)
                return (False, type_map)
            type_map[nam] = typ
        return (True, type_map)
    def __init__(self, procedures, global_variables, local_variables):
        self.procedures = procedures
        self.global_variables: dict = global_variables
        self.local_variables: dict = local_variables or {}
    def normal_variable(self, name):
        result = self.local_variables.get(name)
        if result is not None:
            return result
        return self.global_variables.get(name)
    def check_body(self, decls, statements, message) -> bool:
        for dec in decls:
            if "value" in dec and not self.check_expression(dec["value"], self.normal_variable(dec["name"])):
                print(message)
                return False
        for stmt in statements["argument"]:
            if not self.check_stmt(stmt):
                print(message)
                return False
        return True
    def check_stmt(self, stmt) -> bool:
        match stmt["type"]:
            case "if":
                return self.check_if(stmt)
            case "while":
                return self.check_while(stmt)
            case "do-until":
                return self.check_do_until(stmt)
            case "for-step":
                return self.check_for_step(stmt)
            case "switch":
                return self.check_case(stmt)
            case "set":
                return self.check_set(stmt)
            case "input":
                return self.check_input(stmt)
            case "output":
                return self.check_output(stmt)
            case "call":
                return self.check_call(stmt)
            case x:
                raise NotImplementedError(x)
    def check_if(self, stmt) -> bool:
        return (self.check_expression(stmt["condition"], "bool")
                and self.check_body((), stmt["then"], "type check failed in then-branch of if statement")
                and self.check_body((), stmt["else"], "type check failed in else-branch of if statement"))
    def check_while(self, stmt) -> bool:
        return (self.check_expression(stmt["condition"], "bool")
                and self.check_body((), stmt["body"], "type check failed in while body"))
    def check_do_until(self, stmt) -> bool:
        return (self.check_expression(stmt["condition"], "bool")
                and self.check_body((), stmt["body"], "type check failed in do-until body"))
    def check_for_step(self, stmt) -> bool:
        if not all(self.check_expression(i, "num") for i in stmt["range"]):
            print("for loop start-stop-step must be numbers")
            return False
        name = stmt["name"]
        if name in self.local_variables:
            print("for loop variable cannot shadow a local variable")
            return False
        self.local_variables[name] = "num"
        result = self.check_body((), stmt["body"], "type check failed in for loop body")
        del self.local_variables[name]
        return result
    def check_case(self, stmt) -> bool:
        argument = stmt["argument"]
        arg_type = self.decide_expression(argument)
        if arg_type is None:
            print(f"invalid case argument: undefined variable {argument}")
            return False
        for case in stmt["cases"]:
            key_type = self.decide_expression(case["key"])
            if key_type != arg_type:
                print(f"type error: case key must be compatible with argument variable {arg_type} {argument}")
                return False
            if not self.check_body((), case["body"], "type check failed in case body"):
                return False
        return self.check_body((), stmt["default"], "type check failed in case default body")
    def check_set(self, stmt) -> bool:
        name: str = stmt["name"]
        if name == name.capitalize() and name != "_"*len(name):
            print("cannot assign to constants (CAPITALIZED-named values)")
            return False
        result = self.decide_expression(stmt["argument"])
        expectation = self.normal_variable(name)
        if result == expectation:
            return True
        if expectation is not None:
            print(f"mismatched type assignment to variable {expectation} {name}")
        elif name in self.procedures:
            print("cannot assign to global procedures")
        else:
            print("could not find assignable variable")
        return False
    def check_input(self, stmt) -> bool:
        if not all(self.u_supports_io(arg, False) for arg in stmt["arguments"]):
            print("invalid input statement found: one or more of these variables cannot store input")
            return False
        if len(stmt["arguments"]) != 1:
            print("invalid input statement found: exactly one variable is supported per input")
        return True
    def check_output(self, stmt) -> bool:
        if not all(self.u_supports_io(arg) for arg in stmt["arguments"]):
            print("invalid output statement found: one or more of these values cannot be printed")
            return False
        return True
    def check_call(self, stmt) -> bool:
        name = stmt["name"]
        typ = self.u_get_id_type(name)
        if not isinstance(typ, tuple):
            print(f"cannot call variable {typ} {name}")
            return False
        if len(typ) != len(stmt["arguments"]):
            print(f"attempted to call proc {name} {typ} with {stmt['arguments']} arguments")
            return False
        for expected, arg in zip(typ, stmt["arguments"]):
            if expected != self.decide_expression(arg):
                print(f"incompatibly typed arguments to proc {name} {typ}")
                return False
        return True
    def u_supports_io(self, expr, allow_const=True) -> bool:
        if expr["type"] in ("num", "string"):
            return allow_const
        if expr["type"] != "identifier":
            return False
        name = expr["name"]
        result = self.u_get_id_type(name)
        while isinstance(result, list):
            result = result[0]
        return result in ("num", "string", type) # "type" means the list has no real elements, only sublists
    def u_get_id_type(self, name) -> str | None:
        expectation = self.normal_variable(name)
        if expectation is None and name in self.procedures:
            return self.procedures[name]
        return expectation
    #
    def check_expression(self, expr, expected_type) -> bool:
        result = self.decide_expression(expr)
        _, ok = type_merge(expected_type, result)
        if not ok:
            print(f"type error: expected {expected_type} but got {result} from expression")
        return ok
    def decide_expression(self, expr) -> str:
        expr_type = expr["type"]
        if expr_type in POSSIBLE_LITERALS:
            return expr_type
        match expr_type:
            case "identifier":
                name = expr["name"]
                typ = self.u_get_id_type(name)
                if typ is None:
                    print(f"name error: undefined variable {name}")
                return typ
            case "prefix":
                right = self.decide_expression(expr["right"])
                if right is type:
                    match op:
                        case "NOT":
                            return "bool"
                        case "-":
                            return "num"
                map = PREFIX_TYPE_MAP[expr["operator"]]
                if right not in map:
                    print(f"type error: {expr['operator']} argument of type {right} not supported")
                    return None
                return map[right]
            case "infix":
                left = self.decide_expression(expr["left"])
                right = self.decide_expression(expr["right"])
                op = expr["operator"]
                # before lists: everything was great. after lists: spaghetti
                if left is type:
                    left = right
                elif right is type:
                    right = left
                # (since all infixes are (x,x) -> y typed)
                if left is type and right is type:
                    match op:
                        case "OR" | "AND":
                            return "bool"
                        case "-" | "*" | "/" | "%":
                            return "num"
                        case "<" | ">" | "<=" | ">=" | "=" | "<>":
                            return "bool"
                        case "+":
                            return type # "num" or "string" or list[x]
                if isinstance(left, list) or isinstance(right, list):
                    if op == "+":
                        result, ok = type_merge(left, right)
                        if ok:
                            return result
                        print("type error: (+) concatenation of incompatible lists")
                        return None
                    print(f"type error: {op} with a list is undefined")
                    return None
                map = INFIX_TYPE_MAP[op]
                if (left, right) not in map:
                    print(f"type error: {op} arguments of type ({left}, {right}) not supported")
                    return None
                return map[(left,right)]
            case "builtin":
                name = expr["name"]
                type_map = BUILTIN_TYPES[name]
                args = []
                for arg in expr["arguments"]:
                    result = self.decide_expression(arg)
                    args.append(result)
                if name in LIST_MORPHIC and isinstance(args[0], list):
                    options = LIST_MORPHIC[name]
                    n = 0
                    buffer = args[0]
                    while isinstance(buffer, list):
                        n += 1
                        buffer = buffer[0]
                    while n > 0:
                        callsign = (n, *args[1:])
                        if callsign in options:
                            output = options[callsign] # output is either the depth of the list or a fixed type
                            if not isinstance(output, int):
                                return output
                            result = args[0]
                            while output > n:
                                result = [result]
                                n += 1
                            while output < n and result is not type:
                                result = result[0]
                                n -= 1
                            return result
                        n -= 1
                    print(f"type error: {name} called with incompatible arguments")
                    return None
                final = type_map.get(tuple(args))
                if final is None:
                    print(f"type error: {name} called with incompatible arguments")
                    return None
                return final
            case "list":
                args = []
                for arg in expr["arguments"]:
                    result = self.decide_expression(arg)
                    args.append(result)
                if len(args) == 0:
                    return [type]
                guess = args.pop()
                for arg in args:
                    guess, ok = type_merge(guess, arg)
                    if not ok:
                        print(f"type error: inconsistent list argument types")
                        return None
                return [guess]
            case "index":
                target = self.decide_expression(expr["target"])
                argument = self.decide_expression(expr["argument"])
                if argument != "num":
                    print(f"type error: {'lists' if target != 'str' else 'strings'} can only be indexed by numbers")
                    return None
                if target == "string":
                    return target
                if isinstance(target, list):
                    return target[0]
                print(f"type error: {target} cannot be indexed into")
                return None
            case x:
                raise NotImplementedError(f"expression type {x} not implemented")

def type_merge(x, y):
    if x == y:
        return (x, True)
    if x is type:
        return (y, True)
    if y is type:
        return (x, True)
    xil = isinstance(x, list)
    if xil != isinstance(y, list):
        return (x, False)
    if xil:
        result, ok = type_merge(x[0], y[0])
        return ([result], ok)
    return (x, x==y)
    


