from psmagic import magic_parse_tree

# there is some irony here that a no-backtrack parser is much harder to maintain and extend than a backtracking parser
# TODO: implement "set x[y] = ..."

# for the AST, this parser will just use
# JSON: type = bool | int | str | list[JSON] | dict[str, JSON]
# the set of all things that can be serialized as JSON without altering any data
# as such, parsed trees can be stored for the type checker & interpreter to read

CHECKER_NAMES = set("isNumeric isChar isWhitespace isUpper isLower length find slice toString toNumber".split())
TYPE_NAMES = set("num string bool".split())
KEYWORDS = CHECKER_NAMES|TYPE_NAMES|set(("AND OR NOT start end return if then else endif"
        " while endwhile do until for to step endfor case default endcase set input output").split())

def build_infix_precedence():
    # an operator precedence table is malformed when any left-side number equals any right-side number
    # one simple invariant is to make all lefts even and all rights odd
    # (2x, 2x+1) is a left-associative operation
    # (2x, 2x-1) is a right-associative operation
    # prefix precedence should have right-like numbers
    # suffix precedence should have left-like numbers
    table = {
        "OR": (10, 11), "AND": (20, 21),
        "+": (50, 51), "-": (50, 51),
        "*": (60, 61), "/": (60, 61), "%": (60, 61)
    }
    # space is left between comparisons and addition for possible bitwise operations
    for op in set("< > <= >= <> =".split()):
        table[op] = (30, 31)
    return table
PREFIX_PRECEDENCE = {"NOT": 21, "-": 51}
INFIX_PRECEDENCE = build_infix_precedence()
INFIX_TREE = lambda op, x, z: {"type": "infix", "operator": op, "left": x, "right": z}
PREFIX_TREE = lambda op, z: {"type": "prefix", "operator": op, "right": z}

def empty_body():
    return {"type": "body", "argument": []}

def literal_type(token: str) -> str | None:
    if token.replace(".", "", 1).isdigit():
        return "num"
    if len(token) >= 2 and token[:1] == "\"" and token[-1:] == "\"":
        return "string"
    if token in {"false", "true"}:
        return "bool"
    return None

def convert_literal(token: str):
    match literal_type(token):
        case "num":
            if "." in token:
                value = float(token)
            else:
                value = int(token)
            return {"type": "num", "value": value}
        case "string":
            return {"type": "string", "value": token[1:-1]}
        case "bool":
            return {"type": "bool", "value": token=="true"}
        case x:
            return {"type": "err", "message": f"invalid literal type ({x})"}

def is_valid_name(name: str) -> bool:
    return name.isalnum() and name[:1].isalpha() and name not in KEYWORDS

class PseudocodeParser:
    def __init__(self, tokens:list[str]):
        self.tokens = tokens
        self.skip_newlines = True # TODO
        self.index = [0]
    def token(self) -> str:
        i: int = self.index[-1]
        while i < len(self.tokens):
            token = self.tokens[i]
            if token == "\n" and self.skip_newlines:
                i += 1
            else:
                self.index[-1] = i
                return token
        self.index[-1] = i
        return ""
    def step(self):
        self.index[-1] += 1
    def nearby_error(self, message):
        print(message)
        print(f"token index={self.index}, nearby tokens: {self.tokens[max(self.index[-1]-5,0):self.index[-1]]}; {self.tokens[self.index[-1]:self.index[-1]+6]}")
        return {"type": "err"}
    # every CONSUME function returns a JSON-style value
    def consume_top_level(self):
        t: str = self.token()
        if t == "":
            return {"type": "done", "message": "EOF"}
        if t == "start":
            self.step()
            declarations = self.consume_declarations()
            statements = self.consume_statements()
            if self.token() != "end":
                return self.nearby_error(f"invalid parse: main 'start' not terminated by 'end'")
            self.step()
            return {"type": "start", "declarations": declarations, "statements": statements}
        kept = self.u_consume_generally([
            ("rule", self.consume_name),
            ("lit", "(", "invalid parse: procedure '{t}' is not followed by '('"),
            ("cycle",
                (")".__ne__, [("rule", self.consume_type), ("rule", self.consume_name)]),
                (",".__eq__, [("lit", ",", "")])),
            ("lit", ")", "expected ')' closing procedure header"),
        ])
        if kept["type"] == "err":
            return kept
        _, args = kept["parts"]
        args = [arg["parts"] for arg in args[::2]] # remove the empty comma lists and unpack successes
        for a,b in args:
            a["name"] = b["name"]
        args = [a for a,_ in args] # repackage elements
        declarations = self.consume_declarations()
        statements = self.consume_statements()
        if self.token() != "return":
            return self.nearby_error(f"invalid parse: procedure '{t}' not terminated by 'return'")
        self.step()
        return {"type": "procedure", "name": t, "arguments":args, "declarations": declarations, "statements": statements}
    def consume_type(self):
        kind = self.token()
        depth = 0
        while kind == "*":
            depth += 1
            self.step()
            kind = self.token()
        if kind not in TYPE_NAMES:
            if depth > 0:
                return self.nearby_error(f"{'*'*depth} must be suffixed by a valid type name")
            return self.nearby_error("a valid type name")
        self.step()
        return {"type": kind, "depth": depth}
    def consume_declarations(self):
        if self.token() != "Declarations":
            return []
        _TYPE_NAMES = TYPE_NAMES
        self.step()
        declarations = []
        kind = self.token()
        while kind in _TYPE_NAMES or kind == "*":
            value = self.consume_type()
            if value["type"] == "err":
                return value
            name = self.token()
            if not is_valid_name(name):
                return self.nearby_error(f"invalid parse; expected declaration: {name} is not a valid name")
            self.step()
            value["name"] = name
            equals = self.token()
            if equals == "=":
                self.step()
                subexpr = self.consume_expression()
                if subexpr["type"] == "err":
                    return subexpr
                value["value"] = subexpr
            declarations.append(value)
            kind = self.token()
        return declarations
    def consume_statements(self):
        statements = []
        while (stmt := self.consume_statement()) and stmt["type"] != "err":
            statements.append(stmt)
        if stmt and stmt["type"] == "err":
            return stmt
        return {"type": "body", "argument": statements}
    def consume_statement(self):
        header = self.token()
        match header:
            case "if":
                return self.consume_if()
            case "while":
                return self.consume_while()
            case "do":
                return self.consume_do()
            case "for":
                return self.consume_for()
            case "case":
                return self.consume_case()
            case "set":
                return self.consume_set()
            case "input":
                return self.consume_input()
            case "output":
                return self.consume_output()
        if is_valid_name(header):
            return self.consume_call()
        return None
    def consume_if(self):
        self.step()
        condition = self.consume_condition()
        if self.token() != "then":
            return self.nearby_error("lack of 'then' after if-condition")
        self.step()
        body = self.consume_statements()
        alternative = empty_body()
        if self.token() == "else":
            self.step()
            alternative = self.consume_statements()
        if self.token() == "endif":
            self.step()
            return {"type": "if", "condition": condition, "then": body, "else": alternative}
        return self.nearby_error("lack of 'endif' or 'else' after if-body")
    def consume_while(self):
        self.step()
        condition = self.consume_condition()
        body = self.consume_statements()
        if self.token() == "endwhile":
            self.step()
            return {"type": "while", "condition": condition, "body": body}
        return self.nearby_error(f"lack of closure on while loop")
    def consume_do(self):
        self.step()
        body = self.consume_statements()
        if self.token() != "until":
            return self.nearby_error("lack of closure on do-until loop")
        self.step()
        condition = self.consume_condition()
        return {"type": "do-until", "condition": condition, "body": body}
    def consume_name(self):
        name = self.token()
        if not is_valid_name(name):
            return {"type": "err", "message": "expected name"}
        self.step()
        return {"type": "identifier", "name": name}
    def consume_case_arg(self):
        return self.u_consume_unit(self.token())
    def consume_for(self):
        kept = self.u_consume_generally([
            ("lit", "for", ""),
            ("rule", self.consume_name),
            ("lit", "=", "expected '=' in for-loop statement"),
            ("rule", self.consume_expression),
            ("lit", "to", "expected 'to' in for-loop statement"),
            ("rule", self.consume_expression),
            ("lit", "step", "expected 'step' in for-loop statement"),
            ("rule", self.consume_expression),
            ("rule", self.consume_statements),
            ("lit", "endfor", "expected 'endfor' closing for-loop body"),
        ])
        if kept["type"] == "err":
            return kept
        name, first_expr, second_expr, third_expr, body = kept["parts"]
        return {"type": "for-step", "name": name["name"], "range": [first_expr, second_expr, third_expr], "body": body}
    def consume_case(self):
        def see_case(token) -> bool:
            return is_valid_name(token) or literal_type(token) is not None
        kept = self.u_consume_generally([
            ("lit", "case", ""),
            ("rule", self.consume_name),
            ("repeat", see_case, [
                ("rule", self.consume_case_arg),
                ("lit", ":", "case parse failed: 'case ...' must be followed by ':'"),
                ("rule", self.consume_statements)
            ]),
            ("maybe", "default".__eq__, [
                ("lit", "default", ""),
                ("lit", ":", "case parse failed: 'default' must be followed by ':'"),
                ("rule", self.consume_statements)
            ]),
            ("lit", "endcase", "case parse failed: missing 'endcase'")
        ])
        if kept["type"] == "err":
            return kept
        name, raw_cases, maybe_default_body = kept["parts"]
        cases = [{"type": "case", "key": raw["parts"][0], "body": raw["parts"][1]} for raw in raw_cases]
        if maybe_default_body:
            default_body = maybe_default_body[0]["parts"][0]
        else:
            default_body = empty_body()
        return {"type": "switch", "argument": name, "cases": cases, "default":default_body}
    def consume_set(self):
        kept = self.u_consume_generally([
            ("lit", "set", ""),
            ("rule", self.consume_name),
            ("lit", "=", "expected '=' in set statement"),
            ("rule", self.consume_expression),
        ])
        if kept["type"] == "err":
            return kept
        name, expr = kept["parts"]
        return {"type": "set", "name": name["name"], "argument": expr}
    def consume_input(self):
        self.step()
        arguments = self.u_consume_comma(False)
        for arg in arguments:
            if arg["type"] == "err":
                return arg
        return {"type": "input", "arguments": arguments}
    def consume_output(self):
        kept = self.u_consume_generally([
            ("lit", "output", ""),
            ("rule", self.consume_expression),
            ("repeat", ",".__eq__, [
                ("lit", ",", ""),
                ("rule", self.consume_expression),
            ])
        ])
        if kept["type"] == "err":
            return kept
        first, rest = kept["parts"]
        arguments = [first] + [i["parts"][0] for i in rest]
        return {"type": "output", "arguments": arguments}
    def u_consume_comma(self, allow_literal: bool):
        '''
        accept anything that resembles a location in memory
        conditionally accept general expressions
        if allow_literal: accept literals as well
        TODO: restructure this to meet the new (above) spec
        current behavior: accept variable names (or also literals, depending)
        '''
        items = []
        token = self.token()
        if not (is_valid_name(token) or allow_literal and literal_type(token) is not None):
            return self.nearby_error("expected variable name"+" or literal"*allow_literal+" for IO statement")
        items.append(self.u_consume_unit(token))
        while self.token() == ",":
            self.step()
            token = self.token()
            if not (is_valid_name(token) or allow_literal and literal_type(token) is not None):
                return self.nearby_error("expected variable name"+" or literal"*allow_literal+" after comma")
            items.append(self.u_consume_unit(token))
        return items
    def consume_call(self):
        '''accept the phrase "name(...)"'''
        name = self.token()
        if not is_valid_name(name):
            return self.nearby_error("completely unexpected token: "+name)
        kept = self.u_consume_generally([
            ("rule", self.consume_name),
            ("lit", "(", "expected '(' to call a procedure"),
            ("cycle",
                (")".__ne__, [("rule", self.consume_expression)]),
                (",".__eq__, [("lit", ",", "")])),
            ("lit", ")", "expected ')' closing procedure call"),
        ])
        if kept["type"] == "err":
            return kept
        name, args = kept["parts"]
        return {"type": "call", "name": name["name"], "arguments": [arg["parts"][0] for arg in args[::2]]}
    def consume_condition(self):
        # in order to save on overhead and complexity: conditions have been folded into expressions.
        # name difference retained in case any useful parse difference arises in the future
        return self.consume_expression()
    def consume_expression(self):
        _INFIX_PRECEDENCE = INFIX_PRECEDENCE
        _PREFIX_PRECEDENCE = PREFIX_PRECEDENCE
        _CHECKER_NAMES = CHECKER_NAMES
        parts = []
        recent_op = True
        while True:
            token = self.token()
            if token in _CHECKER_NAMES:
                self.step()
                subexpr = self.u_consume_generally([
                    ("lit", "(", "expected '(' to call a function"),
                    ("rule", self.consume_expression),
                    ("lit", ")", "expected ')' closing function call"),
                ])
                if subexpr["type"] == "err":
                    return subexpr
                parts.append({"type": "builtin", "name": token, "arguments":subexpr["parts"]})
            if token in _INFIX_PRECEDENCE or token in _PREFIX_PRECEDENCE:
                self.step()
                parts.append(token)
                recent_op = True
                continue
            if not recent_op:
                # this is ONLY here because of the unique case where line breaks are syntactically significant
                # set ... = ... + a
                # b()
                # in this case, the concatenation of 'a b' would be found and '()' following would be found and error
                # future support for value-returning functions contingent on supporting resources
                break
            expr = self.consume_term()
            if expr["type"] == "err":
                break
            parts.append(expr)
            recent_op = False
        # taking lessons from pratt: merge nodes into a tree AFTER finding the leaves for more portable and maintainable algorithms.
        return magic_parse_tree(parts, _INFIX_PRECEDENCE, _PREFIX_PRECEDENCE, INFIX_TREE, PREFIX_TREE)
    def consume_term(self):
        # a term is a part of an expression which can be parsed with no precedence calculations
        atom = self.consume_atom()
        while self.token() == "[":
            suffix = self.u_consume_generally([
                    ("lit", "[", ""),
                    ("rule", self.consume_expression),
                    ("lit", "]", "expected ']' closing index operator"),
                ])
            if suffix["type"] == "err":
                return suffix
            atom = {"type":"index", "target":atom, "argument":suffix["parts"][0]}
        return atom
    def consume_atom(self):
        token = self.token()
        if token == "(":
            old = self.skip_newlines
            self.skip_newlines = True
            self.step()
            expr = self.consume_expression()
            token = self.token()
            self.skip_newlines = old
            if token != ")":
                return self.nearby_error(f"invalid parse; expected closing ')' after: ({expr}")
            self.step()
            return expr
        if token == "[":
            return self.consume_list()
        return self.u_consume_unit(token)
    def consume_list(self):
        kept = self.u_consume_generally([
                    ("lit", "[", ""),
                    ("cycle",
                        ("]".__ne__, [("rule", self.consume_expression)]),
                        (",".__eq__, [("lit", ",", "")])),
                    ("lit", "]", "expected ']' closing list expression"),
                ])
        if kept["type"] == "err":
            return kept
        return {"type": "list", "arguments": [arg["parts"][0] for arg in kept["parts"][0][::2]]}
    def u_consume_unit(self, token):
        # these units are all valid CASE cases.
        if is_valid_name(token):
            self.step()
            return {"type": "identifier", "name": token}
        return self.u_consume_literal(token)
    def u_consume_literal(self, token):
        result = convert_literal(token)
        if result["type"] != "err":
            self.step()
        return result
    def u_consume_generally(self, parts: list[tuple]):
        '''
        ("lit", target, error_message): succeed when self.token() == target
        ("rule", function): function()
        ("maybe", test, rules): [rule result] if test() else []
        ("repeat", test, rules): infinite maybes
        ("cycle", (t, r), (t, r)...):
            keep cycling through the list of (test, rules) pairs
            stop at the first failed test
            "repeat" is a special case of a cycle with only one pair
        '''
        kept = []
        for part in parts:
            match part[0]:
                case "lit":
                    token = self.token()
                    if token != part[1]:
                        return self.nearby_error(part[2])
                    self.step()
                case "rule":
                    result = part[1]()
                    if result["type"] == "err":
                        return result
                    kept.append(result)
                case "maybe":
                    results = []
                    if part[1](self.token()):
                        result = self.u_consume_generally(part[2])
                        if result["type"] == "err":
                            return result
                        results.append(result)
                    kept.append(results)
                case "repeat":
                    results = []
                    while part[1](self.token()):
                        result = self.u_consume_generally(part[2])
                        if result["type"] == "err":
                            return result
                        results.append(result)
                    kept.append(results)
                case "cycle":
                    results = []
                    tr_pairs = part[1:]
                    nofails = True
                    while nofails:
                        for test, rules in tr_pairs:
                            if not test(self.token()):
                                nofails = False
                                break
                            result = self.u_consume_generally(rules)
                            if result["type"] == "err":
                                return result
                            results.append(result)
                    kept.append(results)
                case x:
                    raise NotImplementedError(f"parse instruction '{x}'")
        return {"type": "success", "parts": kept}

def parse(tokens:list[str]):
    instance = PseudocodeParser(tokens)
    parts = []
    while (part := instance.consume_top_level())["type"] != "done":
        parts.append(part)
        if part["type"] == "err":
            break
    return parts

