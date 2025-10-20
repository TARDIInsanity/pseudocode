
test_sample = '''
start
  Declarations
    num i
    InputFile a
    OutputFile b
  open a "source.txt"
  open b "destination.txt"
  input i from a
  output i, "foo bar", i to b
  output i
  close a
  close b
end
'''

test_output = '''
start
  Declarations
    OutputFile out
    string name
    num balance
    num total = 0
  open out "test_output.txt"
  output "enter name. ZZZ to quit."
  input name
  while name <> "ZZZ"
    output "enter balance for", name
    input balance
    set total = total + balance
    output name, balance to out
    output "enter name. ZZZ to quit."
    input name
  endwhile
  output "_total_", total to out
  output "Total: ", total
  close out
end
'''

test_input = '''
start
  Declarations
    InputFile inf
    string line
  open inf "test_output.txt"
  input line from inf
  while NOT eof
    output line
    input line from inf
  endwhile
end
'''

sample = '''
start
  Declarations
    num SIZE = 41
    num content[SIZE]
    string PREFIX = "enter the "
    string ST = "1st"
    string ND = "2nd"
    string RD = "3rd"
    string TH = "th"
    string NUMBER = " number: "
    num indexOnes = 0
    num indexTens = 0
    num response
  do
    set content[1] = content[1] + content[1] + 1
  until content[1] > 10
  while (indexTens * 10 + indexOnes < SIZE)
    prompt([[1],[2],[3]])
    input response
    set content[indexTens * 10 + indexOnes] = response
    set indexOnes = indexOnes + 1
    if indexOnes = 10 then
      set indexOnes = 0
      set indexTens = indexTens + 1
    endif
  endwhile
end

prompt(num arg[3][])
  Declarations
    num x = 0
  if indexTens = 0 then
    case indexOnes
      1: output PREFIX, ST, NUMBER
      2: output PREFIX, ND, NUMBER
      3: output PREFIX, RD, NUMBER
      default: output PREFIX, indexOnes, TH, NUMBER
    endcase
  else
    case indexOnes
      1:
        output PREFIX, indexTens, ST, NUMBER
      2:
        output PREFIX, indexTens, ND, NUMBER
      3:
        output PREFIX, indexTens, RD, NUMBER
      default: output PREFIX, indexTens, indexOnes, TH, NUMBER
    endcase
  endif
  output content
return
'''

old_sample = '''
start
  Declarations
    string PROMPT = "input a number; use 999 to end the program: "
    num SENTINEL = 999
    num count = 0
    num total = 0
    num response
    num responses[3] = [3,4,count]
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
