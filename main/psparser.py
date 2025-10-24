from pslexer import lex
from psmagic import magic_parse_tree

# for the AST, this parser will just use
# JSON: type = bool | int | str | list[JSON] | dict[str, JSON]
# the set of all things that can be serialized as JSON without altering any data
# as such, parsed trees can be stored for the type checker & interpreter to read

TOKEN = tuple[str, str]
TREE = bool | int | str | list["TREE"] | dict[str, "TREE"]
RESULT = tuple[bool, int, TREE]
EOF: TOKEN = ("EOF", "")
PREFERRED_QUOTE = "\""
SIMPLE_TYPES = set("num string float bool InputFile OutputFile".split())
TYPE_NAMES = SIMPLE_TYPES
# the three sets of names
CHECKER_NAMES = set("isNumeric isChar isWhitespace isUpper isLower length find slice toString toNumber".split())
KEYOPS = set("AND OR NOT".split())
KEYWORDS = TYPE_NAMES|set("""proc start Declarations end return
if then else endif while endwhile do until for to step endfor
case default endcase set input from output to open close""".split())

def build_infix_precedence():
    # an operator precedence table is malformed when any left-side number equals any right-side number
    # one simple invariant is to make all lefts even and all rights odd
    # (2x, 2x+1) is a left-associative operation
    # (2x, 2x-1) is a right-associative operation
    # prefix precedence should have right-like numbers
    # suffix precedence shoulf have left-like numbers
    table = {
        "OR": (10, 11), "AND": (20, 21),
        "+": (50, 51), "-": (50, 51),
        "*": (60, 61), "/": (60, 61), "%": (60, 61)
    }
    # space is left between comparisons and addition for possible bitwise operations
    for op in set("< > <= >= <> =".split()):
        table[op] = (30, 31)
    return table
PREFIX_PRECEDENCE = {"NOT": 20, "-": 50}
INFIX_PRECEDENCE = build_infix_precedence()
INFIX_TREE = lambda op, x, z: {"type": "infix", "operator": op, "left": x, "right": z}
PREFIX_TREE = lambda op, z: {"type": "prefix", "operator": op, "right": z}
EMPTY_BODY = {"type": "body", "argument": []}

def literal_type(token: str) -> str | None:
    if token.isdigit():
        return "num"
    if token.replace(".", "", 1).isdigit():
        return "float"
    if token in {"false", "true"}:
        return "bool"
    if len(token) >= 2 and token[0] == token[-1] == PREFERRED_QUOTE:
        return "string"
    return None

def convert_literal_new(token: TOKEN):
    typ, value = token
    match typ:
        case "num":
            return {"type": "num", "value": int(value)}
        case "float":
            return {"type": "float", "value": float(value)}
        case "string":
            return {"type": "string", "value": value[1:-1]}
        case "bool":
            return {"type": "bool", "value": value.lower()=="true"}
        case x:
            raise NotImplementedError(f"invalid literal type ({x})")

def convert_literal(token: str):
    match literal_type(token):
        case "num":
            return {"type": "num", "value": int(token)}
        case "float":
            return {"type": "float", "value": float(token)}
        case "string":
            return {"type": "string", "value": token[1:-1]}
        case "bool":
            return {"type": "bool", "value": token=="true"}
        case x:
            raise NotImplementedError(f"invalid literal type ({x})")

def is_valid_name(name: str) -> bool:
    return name.isalnum() and name[0].isalpha() and name not in KEYWORDS

STACK = []
class Parser:
    @classmethod
    def parse(cls, code: str) -> RESULT:
        tokens = list(lex(code, KEYWORDS, KEYOPS))
        return cls(tokens).p_general(0, ("rule", "file"))
    def __init__(self, src: list[TOKEN]):
        self.src = src
        self.funcs = {
            "magic": self.magic,
        }
    def next_any(self, index) -> TOKEN:
        return self.src[index] if index < len(self.src) else EOF
    def nearby(self, index, message):
        return {"message": message, "stack": STACK, "before": self.src[max(index-5,0):index], "after": self.src[index:index+6]}
    def magic(self, index, tree) -> RESULT:
        if not tree:
            return False, index, tree
        parts = []
        for part in tree:
            match part["type"]:
                case "term":
                    parts.append(part)
                case "op" | "eq":
                    parts.append(part["value"]["value"])
                case x:
                    raise NotImplementedError(f"magic term {repr(x)}")
        result = magic_parse_tree(parts, INFIX_PRECEDENCE, PREFIX_PRECEDENCE, INFIX_TREE, PREFIX_TREE)
        if result["type"] == "err":
            raise SyntaxError(result)
        return True, index, result
    #
    def p_general(self, index, rule) -> RESULT:
        '''
        ("rule", NAME): refer to a rule in GENERAL
        ("filter", (NAME, RULE)): call a function on the successful result of a rule
        ("type", (NAME, ERR)): select token by its type
        ("maybe", RULE): return a list maybe containing one result
        ("repeat", RULE): return a list of successful results
        ("cycle", [RULE...]):
            keep cycling through the list of rules
            stop at the first failed rule
        ("split", (RULE_P, RULE_S, ERR)):
            parse P (S P)* and return it as if it were parsed by cycle
        ("all", ([RULE...], ERR)): require all subrules to succeed
        ("list", (left, right, separator, element, ERR))
            with separator: left cycle(element, separator)? right
            without: left element right
        ("option", ({name:RULE...}, ERR)): tagged union of rules. Order matters.
        ("obligatory", (RULE, ERR)): call an error if the rule fails; used for requiring a quiet-failing rule to pass
        ("ABA", (left, separator, right)):
            left (separator right)? | right
        ERR: if None, fail gracefully, otherwise raise a SyntaxError.
        '''
        original = index
        key, arg = rule
        seen = set()
        STACK.append([])
        while key == "rule":
            STACK[-1].append(arg)
            if arg in seen:
                raise RecursionError(f"definition of rule ({rule[1]}) is part of a trivial cycle")
            seen.add(arg)
            key, arg = self.GENERAL[arg]
        STACK[-1].append(key)
        ttype, tvalue = self.next_any(index)
        match key:
            case "filter":
                name, part = arg
                ok, index, result = self.p_general(index, part)
                if ok:
                    ok, index, result = self.funcs[name](index, result)
                    if ok:
                        STACK.pop()
                        return True, index, result
                STACK.pop()
                return False, original, None
            case "type":
                search, err = arg if isinstance(arg, tuple) else (arg, None)
                if ttype == search:
                    STACK.pop()
                    return True, index+1, {"type": ttype, "value": tvalue}
                if err is None:
                    STACK.pop()
                    return False, index, None
                raise SyntaxError(self.nearby(index, err))
            case "maybe":
                ok, index, result = self.p_general(index, arg)
                results = [result] if ok else []
                STACK.pop()
                return True, index, results
            case "repeat":
                results = []
                while True:
                    ok, index, result = self.p_general(index, arg)
                    if not ok:
                        STACK.pop()
                        return True, index, results
                    results.append(result)
            case "cycle":
                assert arg, "cannot cycle an empty list"
                results = []
                while True:
                    for part in arg:
                        ok, index, result = self.p_general(index, part)
                        if not ok:
                            STACK.pop()
                            return True, index, results
                        results.append(result)
            case "split":
                primary, secondary, err = arg
                ok, index, p = self.p_general(index, primary)
                if not ok:
                    if err is None:
                        STACK.pop()
                        return False, original, None
                    raise SyntaxError(self.nearby(index, err))
                results = []
                while ok:
                    results.append(p)
                    original = index
                    ok, index, s = self.p_general(index, secondary)
                    if ok:
                        results.append(s)
                        ok, index, p = self.p_general(index, primary)
                STACK.pop()
                return True, original, results
            case "all":
                parts, err = arg if isinstance(arg, tuple) else (arg, None)
                results = []
                for part in parts:
                    ok, index, result = self.p_general(index, part)
                    if not ok:
                        if err is None:
                            STACK.pop()
                            return False, original, None
                        raise SyntaxError(self.nearby(index, err))
                    results.append(result)
                STACK.pop()
                return True, index, results
            case "list":
                left, right, sep, elem, err = arg
                ok, index, _ = self.p_general(index, left)
                if not ok:
                    STACK.pop()
                    return False, original, None
                if sep is None:
                    ok, index, result = self.p_general(index, elem)
                else:
                    _, index, result = self.p_general(index, ("cycle", [elem, sep]))
                if ok:
                    ok, index, _ = self.p_general(index, right)
                if not ok:
                    if err is None:
                        STACK.pop()
                        return False, original, None
                    raise SyntaxError(self.nearby(index, err))
                STACK.pop()
                return True, index, result
            case "option":
                parts, err = arg if isinstance(arg, tuple) else (arg, None)
                for name, part in parts.items():
                    ok, index, result = self.p_general(index, part)
                    if ok:
                        STACK.pop()
                        return True, index, {"type": name, "value": result}
                if err is None: 
                    STACK.pop()
                    return False, original, None
                raise SyntaxError(self.nearby(index, err))
            case "obligatory":
                rule, err = arg
                ok, index, result = self.p_general(index, rule)
                if not ok:
                    raise SyntaxError(self.nearby(index, err))
                return ok, index, result
            case "ABA":
                left, sep, right = arg
                results = [None, None]
                ok, index, results[0] = self.p_general(index, left)
                if not ok:
                    results[0] = None
                else:
                    ok, index, _ = self.p_general(index, sep)
                    if not ok:
                        return True, index, results
                ok, index, results[1] = self.p_general(index, right)
                if ok:
                    return True, index, results
                return False, original, None
            case x:
                raise NotImplementedError(f"undefined parse instruction '{x}'")
    GENERAL = {
        "file": ("repeat", ("option", {"start": ("rule", "start"), "procedure": ("rule", "procedure"), "\n": ("type", "\n")})),
        "start": ("all", [("type", "start"), ("rule", "mainbody"), ("type", ("end", "expected 'end' ending main 'start' declaration"))]),
        "procedure": ("all", [("type", "name"), ("list", (("type", "("), ("type", ")"), ("type", ","), ("rule", "predicate"), "expected closing ')' in procedure callsign declaration")), ("rule", "mainbody"), ("type", ("return", "expected 'return' ending procedure declaration"))]),
        "mainbody": ("all", [("type", "indent"), ("maybe", ("rule", "Declarations")), ("cycle", [("type", "\n"), ("rule", "stmt")]), ("type", ("dedent", "main body expected dedent after parsing statements")), ("type", ("\n", "nonsensical token stream: dedents must be followed by '\\n' (newline)"))]),
        "body": ("option", ({"indented":("list", (
            ("type", "indent"), ("type", "dedent"), None,
            ("split", (("rule", "stmt"), ("type", "\n"), "expected valid statement in indented body")),
            "expected dedent ending indented body")), "unindented":("rule", "stmt")}, "expected statements")),
        "if": ("all", [("type", "if"), ("rule", "condition"),
                       ("type", ("then", "expected 'then' after 'if'")),
                       ("obligatory", (("rule", "body"), "then-branch of 'if' failed")),
                       ("maybe", ("rule", "else")), ("maybe", ("type", "\n")),
                       ("type", ("endif", "expected 'endif' closing 'if'"))]),
        "else": ("all", [("type", "\n"), ("type", "else"), ("rule", "body")]),
        "while": ("all", [("type", "while"), ("rule", "condition"),
                          ("obligatory", (("rule", "body"), "then-branch of 'while' failed")),
                          ("maybe", ("type", "\n")), ("type", ("endwhile", "expected 'endwhile' closing 'while'"))]),
        "for": ("all", [("type", "for"), ("type", ("name", "expected varname after 'for'")),
                        ("type", "="), ("rule", "expr"), ("type", ("to", "expected 'to' in 'for' statement")),
                        ("rule", "expr"), ("type", ("step", "expected 'step' in 'for' statement")),
                        ("rule", "expr"), ("rule", "body"), ("maybe", ("type", "\n")),
                        ("type", ("endfor", "expected 'endfor' closing 'for'"))]),
        "case": ("all", [("type", "case"), ("rule", "expr"), ("type", "indent"),
                         ("maybe", ("split", (("rule", "case_case"), ("type", "\n"), None))),
                         ("maybe", ("type", "\n")),
                         ("maybe", ("rule", "default_case")),
                         ("type", "dedent"),
                         ("type", ("\n", "expected 'endcase' on a new line closing 'case'")),
                         ("type", ("endcase", "expected 'endcase' closing 'case'"))
        ]),
                        # TODO: replace the rest of this rule with just (x? '\n'? y? dedent '\n' endcase)
                        #  ("ABA", (
                        #   ("split", (("rule", "case_case"), ("type", "\n"), None)),
                        #   ("type", "\n"),
                        #   ("rule", "default_case"),
                        #   )),
                        #  ("maybe", ("type", "\n")),
                        #  ("type", "dedent"),
                        #  ("maybe", ("type", "\n")),
                        #  ("type", ("endcase", "expected 'endcase' closing 'case'"))]),
        "case_case": ("all", [("rule", "atom"), ("type", (":", "expected colon (:) after a complete atomic expression for 'case'")), ("rule", "body")]),
        "default_case": ("all", [("type", "default"), ("type", (":", "expected colon (:) after 'default'")), ("rule", "body")]),
        "do": ("all", [("type", "do"), ("rule", "body"), ("type", ("\n", "nonsensical token stream: dedents must be followed by '\\n' (newline)")), ("type", ("until", "expected 'until' closing 'do' body")), ("rule", "condition")]),
        "set": ("all", [("type", "set"), ("rule", "lval"), ("type", ("=", "expected '=' after destination of assignment statement")), ("rule", "expr")]),
        "input": ("all", [("type", "input"), ("split", (("type", "name"), ("type", ","), "expected valid destination after 'input'")), ("maybe", ("all", [("type", "from"), ("rule", "atom")]))]),
        "output": ("all", [("type", "output"), ("split", (("rule", "expr"), ("type", ","), "expected valid expression after 'output'")), ("maybe", ("all", [("type", "to"), ("rule", "atom")]))]),
        "open": ("all", [("type", "open"), ("type", "name"), ("rule", "atom")]),
        "close": ("all", [("type", "close"), ("type", "name")]),
        "stmt": ("option", dict([(i, ("rule", i)) for i in "if while for case do set input output open close".split()]+[("exprstmt", ("rule", "term"))])),
        "lval": ("all", [("type", "name"), ("repeat", ("rule", "subscript"))]),
        "subscript": ("list", (("type", "["), ("type", "]"), None, ("rule", "expr"), "expected ']' closing subscript")),
        "condition": ("rule", "expr"),
        "expr": ("filter", ("magic", ("repeat", ("option", {"term": ("rule", "term"), "op": ("type", "op"), "eq": ("type", "=")})))),
        "term": ("all", [("rule", "atom"), ("repeat", ("rule", "suffix"))]),
        "suffix": ("option", {"subscript": ("rule", "subscript"), "call": ("rule", "call")}),
        "atom": ("option", {
            "group": ("list", (("type", "("), ("type", ")"), None, ("rule", "expr"), "expected ')' closing grouping")),
            "list": ("list", (("type", "["), ("type", "]"), ("type", ","), ("rule", "expr"), "expected ']' closing list")),
            "name": ("type", "name"),
            "num": ("type", "literal_num"), "float": ("type", "literal_float"), "string": ("type", "literal_string"), "bool": ("type", "literal_bool"),
            }),
        "call": ("list", (("type", "("), ("type", ")"), ("type", ","), ("rule", "expr"), "expected ')' closing procedure call")),
        "Declarations": ("all", [("type", "Declarations"), ("list", (("type", ("indent", "expected indent after 'Declarations'")), ("type", ("dedent", "expected dedent ending 'Declarations' body")), ("type", "\n"), ("rule", "decline"), "error parsing 'Declarations' body"))]),
        "decline": ("all", [("rule", "predicate"), ("maybe", ("all", [("type", "="), ("rule", "expr")]))]),
        "predicate": ("all", [("rule", "elementtype"), ("type", "name"), ("repeat", ("rule", "arraytypesuffix"))]),
        "arraytypesuffix": ("list", (("type", "["), ("type", "]"), None, ("maybe", ("rule", "expr")), "failed to parse [...] array suffix")),
        # the following are DUBIOUS rules
        "elementtype": ("option", dict([(i, ("type", i)) for i in "bool num float string InputFile OutputFile".split()]+[("proc", ("rule", "proctype"))])),
        # "bool" | "num" | "float" | "string" | PROCTYPE
        "proctype": ("all", [("type", "proc"), ("list", (("type", "("), ("type", ")"), ("type", ","), ("all", [("type", "elementtype"), ("repeat", ("rule", "arraytypesuffix"))]), "proc type parse failed"))]),
        # "proc" "(" (ELEMENTTYPE ARRAYTYPESUFFIX* % ",") ")"
    }

class Postparser:
    @staticmethod
    def head_suffix(head, suffix):
        return {"type": "term", "head": head, "suffix": suffix}
    def __init__(self, tree):
        self.tree = tree
    def __getattribute__(self, name: str):
        try:
            return object.__getattribute__(self, name)
        except AttributeError as a:
            if name.startswith("p_"):
                print(a)
                print(f"def {name}(self, tree):\n        self.test(tree, \"{name[2:]}\")")
                quit()
            raise a
    def _test(self, tree, depth=0):
        if isinstance(tree, dict):
            if "type" not in tree:
                return 'dict', tree.keys()
            if depth <= 0:
                return 'result', tree["type"], "..."
            if "value" in tree:
                return 'result', tree["type"], self._test(tree["value"], depth-1)
            return 'other', tree["type"], tree.keys()
        if isinstance(tree, list):
            return 'list', len(tree), [self._test(i, depth-1) for i in tree]
        return tree
    def test(self, tree, name):
        print(name, self._test(tree, 3))
        quit()
    def p_file(self, tree):
        starts = []
        procedures = []
        for part in tree:
            match part["type"]:
                case "\n":
                    continue
                case "start":
                    starts.append(self.p_start(part["value"]))
                case "procedure":
                    procedures.append(self.p_procedure(part["value"]))
        return {"starts": starts, "procedures": procedures}
    def p_start(self, tree):
        _, mainbody, _ = tree
        return {"type": "start", "body": self.p_mainbody(mainbody)}
    def p_mainbody(self, tree):
        _, maybedec, raw_stmts, _, _ = tree
        decls = []
        if maybedec:
            decls = self.p_declarations(maybedec[0])
        stmts = []
        for stmt in raw_stmts[1::2]:
            stmts.append(self.p_stmt(stmt))
        return {"declarations": decls, "statements": stmts}
    def p_declarations(self, tree):
        _, raw_lines = tree
        lines = []
        for line in raw_lines[::2]:
            lines.append(self.p_decline(line))
        return lines
    def p_decline(self, tree):
        raw_predicate, minitial = tree
        predicate = self.p_predicate(raw_predicate)
        initial = None
        if minitial:
            _, expr = minitial[0]
            initial = self.p_expr(expr)
        return {"predicate": predicate, "initial": initial}
    def p_predicate(self, tree):
        raw_type, varname, raw_suffixes = tree
        element_type = self.p_type(raw_type)
        name = varname["value"]
        suffixes = []
        for suffix in raw_suffixes:
            suffixes.append(self.p_type_suffix(suffix))
        return {"name": name, "element": element_type, "suffixes": suffixes}
    def p_type(self, tree):
        if tree["type"] in SIMPLE_TYPES:
            return {"type": tree["type"]}
        if tree["type"] == "proc":
            raise NotImplementedError("'type' expression beginning with 'proc' (rule 'proctype')")
        raise NotImplementedError(tree["type"])
    def p_condition(self, tree):
        return self.p_expr(tree)
    def p_expr(self, tree):
        match tree["type"]:
            case "term":
                return self.p_term(tree["value"])
            case "infix":
                return INFIX_TREE(tree["operator"], self.p_expr(tree["left"]), self.p_expr(tree["right"]))
            case "prefix":
                return PREFIX_TREE(tree["operator"], self.p_expr(tree["right"]))
            case x:
                raise NotImplementedError(f"expression type {repr(x)}")
    def p_term(self, tree):
        raw_atom, raw_suffixes = tree
        atom = self.p_atom(raw_atom)
        for suff in raw_suffixes:
            atom = self.head_suffix(atom, self.p_suffix(suff))
        return atom
    def p_atom(self, tree):
        x = tree["type"]
        match x:
            case "num" | "float" | "string" | "bool":
                return convert_literal_new((x, tree["value"]["value"]))
            case "name":
                return {"type": x, "value": tree["value"]["value"]}
            case "group":
                return {"type": "group", "value": self.p_expr(tree["value"])}
            case "list":
                elements = []
                for element in tree["value"][::2]:
                    elements.append(self.p_expr(element))
                return {"type": "list", "value": elements}
            case x:
                raise NotImplementedError(f"atom type {repr(x)}")
    def p_type_suffix(self, tree):
        if not tree:
            return {"type": "array", "size": None}
        return {"type": "array", "size": self.p_expr(tree[0])}
    def p_procedure(self, tree):
        raw_name, predicates, mainbody, _ = tree
        name = raw_name["value"]
        args = []
        for pred in predicates:
            args.append(self.p_predicate(pred))
        body = self.p_mainbody(mainbody)
        return {"type": "procedure", "name": name, "args": args, "body": body}
    def p_stmt(self, tree):
        match tree["type"]:
            case "if":
                return self.p_if(tree["value"])
            case "while":
                return self.p_while(tree["value"])
            case "for":
                return self.p_for(tree["value"])
            case "case":
                return self.p_case(tree["value"])
            case "do":
                return self.p_do(tree["value"])
            case "set":
                return self.p_set(tree["value"])
            case "input":
                return self.p_input(tree["value"])
            case "output":
                return self.p_output(tree["value"])
            case "open":
                return self.p_open(tree["value"])
            case "close":
                return self.p_close(tree["value"])
            case "exprstmt":
                return {"type": "exprstmt", "value": self.p_term(tree["value"])}
            case x:
                raise NotImplementedError(x)
    def p_while(self, tree):
        _, raw_cond, raw_body, _, _ = tree
        condition = self.p_condition(raw_cond)
        body = self.p_body(raw_body)
        return {"type": "while", "condition": condition, "body": body}
    def p_do(self, tree):
        _, raw_body, _, _, raw_cond = tree
        condition = self.p_condition(raw_cond)
        body = self.p_body(raw_body)
        return {"type": "do", "condition": condition, "body": body}
    def p_body(self, tree):
        stmts = []
        match tree["type"]:
            case "indented":
                for stmt in tree["value"][::2]:
                    stmts.append(self.p_stmt(stmt))
            case "unindented":
                stmts.append(self.p_stmt(tree["value"]))
            case x:
                raise NotImplementedError(f"body type {repr(x)}")
        return {"type": "body", "statements": stmts}
    def p_suffix(self, tree):
        match tree["type"]:
            case "subscript":
                return {"type": "subscript", "value": self.p_subscript(tree["value"])}
            case "call":
                return {"type": "call", "value": self.p_call(tree["value"])}
            case x:
                raise NotImplementedError(f"suffix type {repr(x)}")
    def p_call(self, tree):
        args = []
        for arg in tree:
            args.append(self.p_expr(arg))
        return args
    def p_input(self, tree):
        _, raw_targets, maybe_file = tree
        file = None
        if maybe_file:
            _, raw_atom = maybe_file[0]
            file = self.p_atom(raw_atom)
        targets = []
        for target in raw_targets[::2]:
            targets.append(target["value"])
        return {"type": "input", "values": targets, "file": file}
    def p_output(self, tree):
        _, raw_targets, maybe_file = tree
        file = None
        if maybe_file:
            _, raw_atom = maybe_file[0]
            file = self.p_atom(raw_atom)
        targets = []
        for target in raw_targets[::2]:
            targets.append(self.p_expr(target))
        return {"type": "output", "values": targets, "file": file}
    def p_lval(self, tree):
        name, subscripts = tree
        if not subscripts:
            return {"type": "variable", "name": name["value"]}
        head = {"type": "name", "value": name["value"]}
        for part in subscripts[:-1]:
            head = self.head_suffix(head, self.p_subscript(part))
        return {"type": "subscript", "head": head, "index": self.p_subscript(subscripts[-1])}
    def p_set(self, tree):
        _, lval, _, expr = tree
        lval = self.p_lval(lval)
        expr = self.p_expr(expr)
        return {"type": "set", "lval": lval, "expr": expr}
    def p_subscript(self, tree):
        return self.p_expr(tree)
    def p_if(self, tree):
        _, raw_cond, _, raw_body, m_else, _, _ = tree
        condition = self.p_condition(raw_cond)
        body = self.p_body(raw_body)
        alternative = None
        if m_else:
            alternative = self.p_else(m_else[0])
        return {"type": "if", "condition": condition, "body": body, "else": alternative}
    def p_else(self, tree):
        _, _, body = tree
        return self.p_body(body)
    def p_case(self, tree):
        _, raw_variable, _, mcases, _, mdefault, _, _, _ = tree
        variable = self.p_expr(raw_variable)
        cases = []
        if mcases:
            for case in mcases[0][::2]:
                cases.append(self.p_case_case(case))
        default = None
        if mdefault:
            default = self.p_default_case(mdefault[0])
        return {"type": "case", "variable": variable, "cases": cases, "default": default}
    def p_case_case(self, tree):
        atom, _, body = tree
        test = self.p_atom(atom)
        body = self.p_body(body)
        return {"type": "case", "test": test, "body": body}
    def p_default_case(self, tree):
        _, _, body = tree
        return self.p_body(body)
    def p_for(self, tree):
        _, name, _, initial, _, final, _, step, raw_body, _, _ = tree
        parts = [
            self.p_expr(initial),
            self.p_expr(final),
            self.p_expr(step),
        ]
        body = self.p_body(raw_body)
        return {"type": "for", "variable": name["value"], "range": parts, "body": body}
    def p_open(self, tree):
        _, name, raw_atom = tree
        atom = self.p_atom(raw_atom)
        return {"type": "open", "name": name["value"], "path": atom}
    def p_close(self, tree):
        _, name = tree
        return {"type": "close", "name": name["value"]}
    GENERAL = {
        "arraytypesuffix": ("list", (("type", "["), ("type", "]"), None, ("maybe", ("rule", "expr")), "failed to parse [...] array suffix")),
        "proctype": ("all", [("type", "proc"), ("list", (("type", "("), ("type", ")"), ("type", ","), ("all", [("type", "elementtype"), ("repeat", ("rule", "arraytypesuffix"))]), "proc type parse failed"))]),
    }

