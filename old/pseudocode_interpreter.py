
from pslexer import newline_lex as lex
from psparser import parse
from pstypecheck import TypeChecker, POSSIBLE_LITERALS

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
    "slice": (lambda s, x, y=None: s[x:y]),
}

def accept_number_input(print_function, input_function, support_float) -> int:
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
    def __init__(self, type, value=None):
        self.type = type
        self.value = value

class Interpreter:
    support_float = False
    @classmethod
    def canonical_input(cls) -> str:
        return input()
    @classmethod
    def canonical_print(cls, *args):
        print(*args)
    def __init__(self, parse_tree):
        start = None
        procedures = {}
        global_variables = {}
        for top_level in parse_tree:
            if top_level["type"] == "start":
                start = top_level
            else:
                procedures[top_level["name"]] = top_level
        self.main_body = start
        self.procedures = procedures
        self.global_variables = global_variables
        self.local_stack = []
    def top_vars(self) -> dict:
        if self.local_stack:
            return self.local_stack[-1]
        return self.global_variables
    def start(self):
        for dec in self.main_body["declarations"]:
            var_type = dec["type"]
            var_name = dec["name"]
            initial_value = dec.get("value")
            if initial_value is not None:
                initial_value = self.eval_expr(initial_value)
            self.global_variables[var_name] = Variable(var_type, initial_value)
        self.do_statement(self.main_body["statements"])
    def call_function(self, code, args):
        new_local = {}
        for pair, arg in zip(code["arguments"], args):
            new_local[pair["name"]] = Variable(pair["type"], arg)
        for dec in code["declarations"]:
            var_type = dec["type"]
            var_name = dec["name"]
            initial_value = dec.get("value")
            new_local[var_name] = Variable(var_type, initial_value)
        self.local_stack.append(new_local)
        self.do_statement(code["statements"])
        self.local_stack.pop(-1)
    def read_var(self, name, allow_garbage=True):
        value = self.get_var(name)
        if value is not None:
            return value.value
        if allow_garbage:
            return None
        raise NameError(f"variable {name} not yet defined")
    def get_var(self, name) -> Variable | None:
        if self.local_stack and name in self.local_stack[-1]:
            return self.local_stack[-1][name]
        if name in self.global_variables:
            return self.global_variables[name]
        if name in self.procedures:
            return Variable("proc", self.procedures[name]) # each time a new variable because these should be immutable
        return None
    def assign_var(self, name, new_value):
        if self.local_stack and name in self.local_stack[-1]:
            self.local_stack[-1][name].value = new_value
            return
        if name in self.global_variables:
            self.global_variables[name].value = new_value
            return
        if name in self.procedures:
            raise ValueError("cannot assign to global constants")
        raise NameError(f"unrecognized name: {name}")
    # statements
    def do_statement(self, stmt):
        match stmt["type"]:
            case "body":
                self.do_body(stmt)
            case "if":
                self.do_if(stmt)
            case "while":
                self.do_while(stmt)
            case "do-until":
                self.do_do_until(stmt)
            case "for-step":
                self.do_for_step(stmt)
            case "switch":
                self.do_switch(stmt)
            case "set":
                self.do_set(stmt)
            case "input":
                self.do_input(stmt)
            case "output":
                self.do_output(stmt)
            case "call":
                self.do_call(stmt)
            case x:
                raise NotImplementedError(f"statement type '{x}'")
    def do_body(self, stmt):
        for sub in stmt["argument"]:
            self.do_statement(sub)
    def do_if(self, stmt):
        branch = stmt["else"]
        condition = self.eval_expr(stmt["condition"])
        if condition:
            branch = stmt["then"]
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
        var_name = stmt["name"]
        if step_val == 0:
            raise ZeroDivisionError("step value cannot be zero")
        if (start_val == stop_val) or (start_val < stop_val) != (0 < step_val):
            return # empty range
        negative = step_val < 0
        if negative: # ensure the loop condition comparison works as expected
            step_val = -step_val
            start_val = -start_val
            stop_val = -stop_val
        index = 0
        parameter = start_val
        current_local = self.top_vars()
        # why go through all this trouble?
        # python doesn't support float ranges;
        # this is the most stable and error-resistant way to implement them
        while parameter < stop_val:
            if negative:
                parameter = -parameter
            current_local[var_name] = Variable("num", parameter)
            self.do_statement(stmt["body"])
            index += 1
            parameter = start_val + step_val * index
        # in case the loop never triggered for any reason, check
        if var_name in current_local:
            del current_local[var_name]
    def do_switch(self, stmt):
        argument = stmt["argument"]
        arg_value = self.eval_expr(argument)
        chosen_body = stmt["default"]
        for case in stmt["cases"]:
            case_key = self.eval_expr(case["key"])
            if case_key == arg_value:
                chosen_body = case["body"]
                break
        self.do_statement(chosen_body)
    def do_set(self, stmt):
        new_value = self.eval_expr(stmt["argument"])
        self.assign_var(stmt["name"], new_value)
    def do_input(self, stmt):
        variables = []
        #seen = set()
        for var in stmt["arguments"]:
            var_name = var["name"]
            # if var_name in seen:
            #     raise ValueError("cannot input to the same variable multiple times at once")
            # seen.add(var_name)
            variables.append(self.get_var(var_name))
        if len(variables) != 1:
            raise NotImplementedError("only one input is supported currently")
        only_var: Variable = variables[0]
        match only_var.type:
            case "string":
                only_var.value = self.canonical_input()
            case "num":
                only_var.value = accept_number_input(self.canonical_print, self.canonical_input, self.support_float)
            case x:
                raise NotImplementedError(f"input for type '{x}' not supported")
    def do_output(self, stmt):
        parts = []
        for part in stmt["arguments"]:
            parts.append(self.eval_expr(part))
        self.canonical_print(*parts) # assume type check has validated this
    def do_call(self, stmt):
        code = self.read_var(stmt["name"], False)
        args = []
        for arg in stmt["arguments"]:
            args.append(self.eval_expr(arg))
        self.call_function(code, args)
    # expressions
    def eval_expr(self, expr):
        expr_type = expr["type"]
        if expr_type in POSSIBLE_LITERALS:
            return expr["value"]
        match expr_type:
            case "identifier":
                return self.read_var(expr["name"])
            case "prefix":
                right = self.eval_expr(expr["right"])
                return self.function_prefix(expr["operator"], right)
            case "infix":
                op = expr["operator"]
                left = self.eval_expr(expr["left"])
                if op in ("OR", "AND") and left == (op == "OR"):
                    return left
                right = self.eval_expr(expr["right"])
                if op in ("OR", "AND"):
                    return right
                return self.function_infix(expr["operator"], left, right)
            case "builtin":
                function = BUILTINS[expr["name"]]
                args = []
                for arg in expr["arguments"]:
                    args.append(self.eval_expr(arg))
                return function(*args)
            case "list":
                args = []
                for arg in expr["arguments"]:
                    args.append(self.eval_expr(arg))
                return args
            case "index":
                target = self.eval_expr(expr["target"])
                argument = self.eval_expr(expr["argument"])
                return target[argument]
            case x:
                raise NotImplementedError(f"expression type '{x}' not implemented")
    #
    def function_prefix(self, op: str, right):
        match op:
            case "NOT":
                return not right
            case "-":
                return -right
            case x:
                raise NotImplementedError(f"prefix '{x}' not implemented")
    def function_infix(self, op: str, left, right):
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

interpreter_tests = ['''
start
  Declarations
    num i
  input i
  output i, "foo bar", i
  output i
end
''']

sample = '''
start
  Declarations
    string PROMPT = "input a number; use 999 to end the program: "
    num SENTINEL = 999
    num count = 0
    num total = 0
    num response
    *num responses = [3,4,count]
  set responses = responses + responses
  larpy()
  fooBar(0)
  fooBar(3)
  fooBar(5)
  for iota = 3 to 9 step 2
    output iota
  endfor
  case total
    3: output 4
    4: output 5
    default: set total = 8
  endcase
  output PROMPT
  // the program assumes user inputs are all valid numbers
  input response
  while response <> SENTINEL
    set count = count + 1
    set total = total + response
    set responses = responses + [response]
    output PROMPT
    input response
  endwhile
  output responses
  output count, total
end

larpy()
  Declarations
    string response
    num result
  output "say something"
  input response
  set result = length(response)
  output "response length:", result
  if isNumeric(response) then
    output "that was a number"
  endif
return

fooBar(num y)
  Declarations
    num fizz
    num buzz
    num x
    num attempts = 3
  set x = y
  while x = y AND attempts > 0
    set attempts = attempts - 1
    output "type a number other than", y
    input x
  endwhile
  if x = y then
    if y = 0 then
      output "assuming 15"
      set x = 15
    else
      output "assuming 0"
      set x = 0
    endif
  endif
  set fizz = x
  set buzz = x
  while fizz >= 5
    set fizz = fizz - 5
  endwhile
  while buzz >= 3
    set buzz = buzz - 3
  endwhile
  if fizz = 0 then
    if buzz = 0 then
        output "fizzbuzz"
    else
        output "fizz"
    endif
  else
    if buzz = 0 then
        output "buzz"
    else
        output x
    endif
  endif
return
'''

def main():
    tree = parse(list(lex(sample)))
    #print(tree)
    type_map = TypeChecker.check_program(tree)
    if type_map is not None:
        # type_map not necessary for interpretation, but if it fails then the interpreted program would also fail
        interpreter = Interpreter(tree)
        interpreter.start()
    else:
        print("type check failed")
    print("input nothing to exit")
    while (i := input()):
        try:
            exec(i)
        except Exception as e:
            print(e)
            print("input nothing to exit")

if __name__ == "__main__":
    main()
