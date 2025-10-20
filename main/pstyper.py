
# TODO: change all type signatures to use Type instances

SIMPLE_TYPES = set("num string float bool InputFile OutputFile".split())

# TODO: generalize 'eof' to derive from a set of reserved names

class Type:
    def merge(self, _):
        # 'merge' assumes merging is valid!
        raise NotImplementedError
    def printable(self) -> bool:
        return False
    def fmtable(self) -> bool:
        return False
    def get_garbage(self):
        '''for container types with nonempty initial states'''
        raise NotImplementedError
MERGE = tuple[bool, Type]
class Any(Type):
    BUFFER = None
    def __new__(cls):
        if cls.BUFFER is None:
            cls.BUFFER = super().__new__(cls)
        return cls.BUFFER
    def __hash__(self):
        return NotImplemented
    def __eq__(self, _):
        return True
    def merge(self, other) -> Type:
        return other
class Basic(Type):
    BUFFER = {}
    def __new__(cls, name: str):
        if name in cls.BUFFER:
            return cls.BUFFER[name]
        instance = super().__new__(cls)
        instance.__init__(name)
        cls.BUFFER[name] = instance
        return instance
    def __init__(self, name: str):
        self.name = name
    def __repr__(self):
        return f"Basic({repr(self.name)})"
    def __eq__(self, other):
        return self is other or other is Any()
    def merge(self, _) -> Type:
        return self
    def printable(self) -> bool:
        return self.name in "bool num float string".split()
    def fmtable(self) -> bool:
        return self.name in "bool num float string".split()
    def get_garbage(self):
        return None
class List(Type):
    def __init__(self, elem: Type, static_size: int|None = None):
        self.elem = elem
        self.static_size = static_size
    def __repr__(self):
        return f"[{repr(self.elem)}]"
    def __eq__(self, other):
        return isinstance(other, List) and self.elem == other.elem or other is Any()
    def merge(self, other) -> Type:
        if other is Any():
            return self
        return List(self.elem.merge(other.elem))
    def printable(self) -> bool:
        return self.elem.printable()
    def fmtable(self) -> bool:
        if self.elem in [Basic("bool"), Basic("num"), Basic("float")]:
            return True
        return False
    def get_garbage(self):
        if self.static_size is None:
            return []
        e = self.elem
        return [e.get_garbage() for _ in range(self.static_size)]
class Procedure(Type):
    def __init__(self, args: list[Type]):
        self.args = args
    def __repr__(self):
        return f"proc{repr(tuple(self.args))}"
    def __eq__(self, other):
        if not isinstance(other, Procedure) or len(self.args) != len(other.args):
            return other is Any()
        for a,b in zip(self.args, other.args):
            if a != b:
                return False
        return True
    def merge(self, other) -> Type:
        if other is Any():
            return self
        args = []
        for a,b in zip(self.args, other.args):
            args.append(a.merge(b))
        return Procedure(args)
    def get_garbage(self):
        return None
class Function(Type):
    def __init__(self, args: list[Type], result: Type):
        self.args = args
        self.result = result
    def __repr__(self):
        return f"{repr(self.result)}{repr(tuple(self.args))}"
    def __eq__(self, other):
        if not isinstance(other, Function) or len(self.args) != len(other.args):
            return other is Any()
        for a,b in zip(self.args, other.args):
            if a != b:
                return False
        return self.result == other.result
    def merge(self, other) -> Type:
        if other is Any():
            return self
        args = []
        for a,b in zip(self.args, other.args):
            args.append(a.merge(b))
        return Function(args, self.result.merge(other.result))
    def get_garbage(self):
        return None
class ListFunction(Type):
    BUFFER = {}
    def __new__(cls, name: str):
        if name in cls.BUFFER:
            return cls.BUFFER[name]
        instance = super().__new__(cls)
        instance.__init__(name)
        cls.BUFFER[name] = instance
        return instance
    def __init__(self, name: str):
        self.name = name
    def __repr__(self):
        return f"ListFunction({repr(self.name)})"
    def __eq__(self, other):
        return self is other
    def merge(self, _) -> Type:
        return self
    def get_garbage(self):
        return None

def build_builtins():
    '''
    INFIX_TYPES: dict[str, list[Function]]
    PREFIX_TYPES: dict[str, list[Function]]
        search the list of functions for a compatible signature when testing types
    BUILTIN_FUNCTIONS: dict[str, Function]
        builtins, with rare exceptions, must behave like user-defined functions:
            you only get one type signature.
    LIST_FUNCTIONS: set[str]
        a simple accounting of the exceptions
    '''
    for i in "bool num float string InputFile OutputFile".split():
        Basic(i)
    INFIX_TYPES = dict((op, []) for op in "OR AND + - * / % < > <= >= = <>".split())
    fb = Function([Basic("bool"), Basic("bool")], Basic("bool"))
    for op in "OR AND = <>".split():
        INFIX_TYPES[op].append(fb)
    fb = [Function([Basic(i), Basic(i)], Basic(i)) for i in "num float".split()]
    for op in "+ - * / %".split():
        INFIX_TYPES[op] += fb
    INFIX_TYPES["+"].append(Function([Basic("string"), Basic("string")], Basic("string")))
    fb = [Function([Basic(i), Basic(i)], Basic("bool")) for i in "num float string".split()]
    for op in "< > <= >= = <>".split():
        INFIX_TYPES[op] += fb
    PREFIX_TYPES = {
        "NOT": [Function([Basic("bool")], Basic("bool"))],
        "-": [Function([Basic(i)], Basic(i)) for i in "num float".split()],
    }
    BUILTIN_FUNCTIONS = {}
    fb = Function([Basic("string")], Basic("bool"))
    for name in "isNumeric isChar isWhitespace isUpper isLower".split():
        BUILTIN_FUNCTIONS[name] = fb
    BUILTIN_FUNCTIONS["toNumber"] = Function([Basic("string")], Basic("num"))
    BUILTIN_FUNCTIONS["find"] = Function([Basic("string"), Basic("string")], Basic("num"))
    BUILTIN_FUNCTIONS["toString"] = Function([Basic("num")], Basic("string"))
    # list functions work on strings too
    LIST_FUNCTIONS = {"length", "getFirst", "getLast", "getBetween"}
    return INFIX_TYPES, PREFIX_TYPES, BUILTIN_FUNCTIONS, LIST_FUNCTIONS
INFIX_TYPES, PREFIX_TYPES, BUILTIN_FUNCTIONS, LIST_FUNCTIONS = build_builtins()

TYPE_MAP = dict[str, Type]
EXPR_RESULT = Type

class TypeChecker:
    def __getattribute__(self, name: str):
        try:
            return object.__getattribute__(self, name)
        except AttributeError as a:
            if name.startswith("p_"):
                print(a)
                print(f"def {name}(self, tree) -> _RESULT:\n        print(\"NotImplemented: {name[2:]}\")\n        quit()")
                quit()
            raise a
    def __init__(self, constants: TYPE_MAP, global_variables: TYPE_MAP):
        '''
        constants:
            all builtin functions
            all globally defined procedures
            all constant values declared in the START block
        global_variables:
            all variables declared in the START block
        '''
        self.con = [constants]
        self.var = [global_variables]
    def append(self, con: TYPE_MAP, var: TYPE_MAP):
        self.con.append(con)
        self.var.append(var)
    def pop(self) -> tuple[TYPE_MAP, TYPE_MAP]:
        con = self.con.pop()
        var = self.var.pop()
        return con, var
    def read_var(self, name:str, only_writable:bool=False) -> Type:
        if name in LIST_FUNCTIONS:
            return ListFunction(name)
        if name in BUILTIN_FUNCTIONS:
            return BUILTIN_FUNCTIONS[name]
        if only_writable and name == "eof":
            raise TypeError("'eof' is a reserved variable and cannot be manually assigned to")
        if name.upper() != name:
            for src in reversed(self.var):
                if name in src:
                    return src[name]
        if not only_writable:
            for src in reversed(self.con):
                if name in src:
                    return src[name]
        raise NameError(f"undeclared name: {repr(name)}")
    # DECIDERS
    def decide_subscript_type(self, head: Type, index: Type) -> Type:
        if isinstance(head, List):
            if index != Basic("num"):
                raise TypeError("list index must be an integer")
            return head.elem
        if head == Basic("string"):
            return Basic("string")
        raise TypeError("only list[num] and string[num] subscripting are supported")
    def decide_call_type(self, head: Type, args: list[Type]) -> Type:
        if isinstance(head, ListFunction):
            return self.decide_list_function(head.name, args)
        ihp = isinstance(head, Procedure)
        ihf = isinstance(head, Function)
        if not (ihp or ihf):
            raise TypeError("calling a non-callable type")
        if head.args != args:
            raise TypeError(f"{'procedure' if ihp else 'function'} called with incompatibly typed arguments")
        if ihp:
            return Basic("_void_")
        return head.result
    def decide_list_function(self, name: str, args: list[Type]) -> Type:
        match name:
            case "length": # [list[x]] -> num
                if len(args) != 1 or args[0] not in (List(Any()), Basic("string")):
                    raise TypeError("'length' function only accepts lists and strings")
                return Basic("num")
            case "getFirst" | "getLast": # [list[x], num] -> list[x]
                if len(args) != 2 or args[0] not in (List(Any()), Basic("string")) or args[1] != Basic("num"):
                    raise TypeError(f"'{name}' function only accepts lists and strings with a single number index")
                return args[0]
            case "getBetween": # [list[x], num, num] -> list[x]
                if len(args) != 3 or args[0] not in (List(Any()), Basic("string")) or args[1:] != [Basic("num"), Basic("num")]:
                    raise TypeError(f"'getBetween' function only accepts lists and strings followed by two numbers")
                return args[0]
            case _:
                raise NotImplementedError(f"builtin list-function {repr(name)}")
    # THE MAIN FILE / DECLARATIONS
    def gather_decls(self, declarations, con: TYPE_MAP, var: TYPE_MAP) -> tuple[TYPE_MAP, TYPE_MAP]:
        self.append(con ,var)
        for decl in declarations:
            pred, raw_initial = decl["predicate"], decl["initial"]
            element = self.gather_predicate(pred)
            name = pred["name"]
            if name == "eof":
                raise NameError("'eof' is a reserved (bool) variable name")
            elif name == name.upper():
                con[name] = element
            else:
                var[name] = element
            if raw_initial is not None and self.check_expr(raw_initial) != element:
                raise TypeError(f"invalid initialization for {repr(name)}")
        return self.pop()
    def gather_proctype(self, raw_args) -> tuple[Procedure, tuple[TYPE_MAP, TYPE_MAP]]:
        con = {}
        var = {}
        self.append(con ,var)
        args = []
        for arg in raw_args:
            element = self.gather_predicate(arg)
            name = arg["name"]
            if name == "eof":
                raise NameError("'eof' is a reserved (bool) variable name")
            elif name == name.upper():
                con[name] = element
            else:
                var[name] = element
            args.append(element)
        return Procedure(args), self.pop()
    def gather_predicate(self, pred):
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
                if size is not None and self.check_expr(size) != Basic("num"):
                    raise TypeError("array sizes must be integers ('num' type)")
                return List(elem)
            case x:
                raise NotImplementedError(f"type-suffix {repr(x)}")
    #
    @classmethod
    def check_file(cls, tree):
        starts = tree["starts"]
        if len(starts) > 1:
            raise TypeError("multiple 'start' points defined")
        if not starts:
            raise TypeError("program lacks 'start' point")
        start = starts[0]
        constants, global_variables = cls({}, {}).gather_decls(start["body"]["declarations"], {}, {"eof":Basic("bool")})
        instance = cls(constants, global_variables)
        partial_decls = {}
        for proc in tree["procedures"]:
            name = proc["name"]
            constants[name], partial_decls[name] = instance.gather_proctype(proc["args"])
        instance.check_body(start["body"])
        for proc in tree["procedures"]:
            con, var = instance.gather_decls(proc["body"]["declarations"], *partial_decls[name])
            instance.append(con, var)
            instance.check_body(proc["body"])
            instance.pop()
        return constants, global_variables, partial_decls
    # STMT
    def check_body(self, body):
        for stmt in body["statements"]:
            self.check_stmt(stmt)
    check_else = check_body
    def check_stmt(self, stmt):
        match stmt["type"]:
            case "if":
                return self.check_if(stmt)
            case "while" | "do":
                return self.check_while(stmt)
            case "for":
                return self.check_for(stmt)
            case "case":
                return self.check_case(stmt)
            case "set":
                return self.check_set(stmt)
            case "input":
                return self.check_input(stmt)
            case "output":
                return self.check_output(stmt)
            case "open":
                return self.check_open(stmt)
            case "close":
                return self.check_close(stmt)
            case "exprstmt":
                # procedures return _void_ which can only appear here, where types aren't checked
                # _void_ is incompatible with all types, including itself, like float('Nan')
                self.check_term(stmt["value"])
            case x:
                raise NotImplementedError(x)
    def check_if(self, stmt):
        if self.check_cond(stmt["condition"]) != Basic("bool"):
            raise TypeError(f"'if' condition must evaluate to a boolean")
        self.check_body(stmt["body"])
        alternative = stmt["else"]
        if alternative is not None:
            self.check_else(alternative)
    def check_while(self, stmt):
        if self.check_cond(stmt["condition"]) != Basic("bool"):
            raise TypeError(f"'while' condition must evaluate to a boolean")
        self.check_body(stmt["body"])
    def check_for(self, stmt):
        parts = []
        for i in stmt["range"]:
            parts.append(self.check_expr(i))
        if not (parts[0] == Basic("num") or parts[0] == Basic("float")):
            raise TypeError("'for-step' loop variables must be numeric")
        if not (parts[0] == parts[1] == parts[2]):
            raise TypeError("'for-step' loop end & step values must be numeric and match the initial type")
        self.append({}, {stmt["variable"]: parts[0]})
        self.check_body(stmt["body"])
        self.pop()
    def check_case(self, stmt):
        argument = self.check_expr(stmt["variable"])
        for case in stmt["cases"]:
            if self.check_atom(case["test"]) != argument:
                raise TypeError("'case' test-value type mismatch")
            self.check_body(case["body"])
        if stmt["default"] is not None:
            self.check_body(stmt["default"])
    def check_input(self, stmt):
        if stmt["file"] is not None:
            if self.check_atom(stmt["file"]) != Basic("InputFile"):
                raise TypeError("'input-from' can only draw from 'InputFile'")
        targets = []
        for target in stmt["values"]:
            targets.append(self.read_var(target, True))
        if not all(i.fmtable() for i in targets):
            raise TypeError("inputting is limited to builtin format options (basic types or lists of bool, num, float)")
        seen = []
        for i in targets:
            if isinstance(i, List):
                if i.elem in seen:
                    raise TypeError("inputting to multiple lists of the same element type")
                seen.append(i.elem)
    def check_output(self, stmt):
        if stmt["file"] is not None:
            if self.check_atom(stmt["file"]) != Basic("OutputFile"):
                raise TypeError("'output-to' can only write to 'OutputFile'")
        targets = []
        for target in stmt["values"]:
            targets.append(self.check_expr(target))
        if not all(i.printable() for i in targets):
            raise TypeError("outputting an unprintable type")
    def check_open(self, stmt):
        if self.read_var(stmt["name"]) not in [Basic("InputFile"), Basic("OutputFile")]:
            raise TypeError("cannot open a file into a non-file variable")
        if self.check_atom(stmt["path"]) != Basic("string"):
            raise TypeError("filepaths must be strings")
    def check_close(self, stmt):
        if self.read_var(stmt["name"]) not in [Basic("InputFile"), Basic("OutputFile")]:
            raise TypeError("cannot close a non-file variable")
    def check_set(self, stmt):
        right = self.check_expr(stmt["expr"])
        left = self.check_lval(stmt["lval"])
        if left != right:
            raise TypeError("invalid assignment")
    # special
    def apply_suffix(self, head, suff) -> Type:
        match suff["type"]:
            case "subscript": # x[y]
                index = self.check_expr(suff["value"])
                return self.decide_subscript_type(head, index)
            case "call": # x(...)
                args = []
                for arg in suff["value"]:
                    args.append(self.check_expr(arg))
                return self.decide_call_type(head, args)
            case x:
                raise NotImplementedError(f"suffix type {repr(x)}")
    # EXPR
    def check_cond(self, cond) -> Type:
        return self.check_expr(cond)
    def check_expr(self, expr) -> Type:
        match expr["type"]:
            case "infix":
                op = expr["operator"]
                left = self.check_expr(expr["left"])
                right = self.check_expr(expr["right"])
                if op not in INFIX_TYPES:
                    raise NotImplementedError(f"infix type {repr(op)}")
                if op == "+" and left == right == List(Any()):
                    return left.merge(right)
                for ftype in INFIX_TYPES[op]:
                    if [left, right] == ftype.args:
                        return ftype.result
                raise TypeError(f"invalid operand types for infix {repr(op)}")
            case "prefix":
                op = expr["operator"]
                right = self.check_expr(expr["right"])
                if op not in PREFIX_TYPES:
                    raise NotImplementedError(f"prefix type {repr(op)}")
                for ftype in PREFIX_TYPES[op]:
                    if [right] == ftype.args:
                        return ftype.result
                raise TypeError(f"invalid operand types for prefix {repr(op)}")
            case _:
                return self.check_term(expr)
    def check_term(self, term) -> Type:
        suffixes = []
        while term["type"] == "term":
            suffixes.append(term["suffix"])
            term = term["head"]
        head = self.check_atom(term)
        for suff in reversed(suffixes):
            head = self.apply_suffix(head, suff)
        return head
    def check_atom(self, atom) -> Type:
        x = atom["type"]
        match x:
            case "num" | "float" | "string" | "bool":
                return Basic(x)
            case "name":
                return self.read_var(atom["value"])
            case "group":
                return self.check_expr(atom["value"])
            case "list":
                elements = []
                for e in atom["value"]:
                    elements.append(self.check_expr(e))
                if not elements:
                    return List(Any())
                first = elements.pop()
                for e in elements:
                    if first != e:
                        raise TypeError("incompatible elements of a list")
                    first = first.merge(e)
                return List(first)
            case x:
                raise NotImplementedError(f"atom type {repr(x)}")
    def check_lval(self, lval) -> Type:
        match lval["type"]:
            case "variable":
                return self.read_var(lval["name"], True)
            case "subscript":
                head = self.check_term(lval["head"])
                index = self.check_expr(lval["index"])
                return self.decide_subscript_type(head, index)
            case x:
                raise NotImplementedError(f"lval type {repr(x)}")
