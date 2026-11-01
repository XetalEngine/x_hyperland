"""Integer arithmetic and calculator state, independent of the interface.

Every operation uses a signed, fixed-width two's-complement word. Hexadecimal
shows the underlying unsigned bit pattern. No floating point or eval is used.
"""

from dataclasses import dataclass
import re


class CalculatorError(ValueError):
    """A recoverable input or arithmetic error."""


OPERATORS = {"OR": 1, "XOR": 2, "AND": 3, "<<": 4, ">>": 4,
             "+": 5, "-": 5, "*": 6, "/": 6, "MOD": 6}
SYMBOLS = {"*": "×", "/": "÷", "-": "−", "<<": "≪", ">>": "≫"}


@dataclass(frozen=True)
class HistoryEntry:
    expression: str
    result: int
    base: int
    bits: int


def format_number(value: int, base: int = 10, bits: int = 64,
                  grouped: bool = False) -> str:
    if base == 16:
        text = format(value & ((1 << bits) - 1), "X")
        if grouped:
            first = len(text) % 4 or 4
            return " ".join([text[:first]] + [text[i:i + 4]
                                             for i in range(first, len(text), 4)])
        return text
    return format(value, ",") if grouped else str(value)


class Calculator:
    MAX_TOKENS = 160

    def __init__(self, bits: int = 64, base: int = 10):
        if bits not in (8, 16, 32, 64) or base not in (10, 16):
            raise ValueError("Unsupported word size or base")
        self.bits = bits
        self.base = base
        self.history: list[HistoryEntry] = []
        self.clear()

    @property
    def mask(self) -> int:
        return (1 << self.bits) - 1

    def normalize(self, value: int) -> int:
        value &= self.mask
        return value - (1 << self.bits) if value >> (self.bits - 1) else value

    def formatted(self, base: int | None = None, grouped: bool = False) -> str:
        return format_number(self.value, base or self.base, self.bits, grouped)

    def clear(self) -> None:
        self.value = 0
        self.entry: str | None = "0"
        self.tokens: list[int | str] = []
        self.just_evaluated = False
        self.last_expression = ""
        self.repeat: tuple[str, int] | None = None

    def _start_entry(self) -> None:
        if self.just_evaluated:
            self.tokens = []
            self.entry = None
            self.just_evaluated = False
            self.repeat = None
            self.last_expression = ""
        if self.entry is None and self.tokens and self.tokens[-1] == ")":
            self._check_length()
            self.tokens.append("*")

    def _check_length(self) -> None:
        if len(self.tokens) >= self.MAX_TOKENS:
            raise CalculatorError("Expression is too long")

    def input_digit(self, digit: str) -> None:
        digit = digit.upper()
        if len(digit) != 1 or digit not in "0123456789ABCDEF"[:self.base]:
            return
        # Validate before mutating state, so a rejected digit preserves the input.
        prefix = "" if self.just_evaluated else (self.entry or "")
        negative = prefix.startswith("-")
        magnitude = (prefix.lstrip("-").lstrip("0") + digit) or "0"
        candidate = ("-" if negative else "") + magnitude
        raw = int(candidate, self.base)
        maximum = self.mask if self.base == 16 else (1 << (self.bits - 1)) - 1
        if not -(1 << (self.bits - 1)) <= raw <= maximum:
            raise CalculatorError(f"Input exceeds {self.bits}-bit range")
        self._start_entry()
        self.entry = candidate
        self.value = self.normalize(raw)
        self.last_expression = ""

    def _commit_entry(self) -> None:
        if self.entry is not None:
            self._check_length()
            self.tokens.append(self.value)
            self.entry = None

    def operator(self, operator: str) -> None:
        if operator not in OPERATORS:
            raise ValueError("Unknown operator")
        self._check_length()
        self.just_evaluated = False
        self.repeat = None
        self.last_expression = ""
        self._commit_entry()
        if not self.tokens:
            self.tokens.append(self.value)
        if self.tokens[-1] in OPERATORS:
            self.tokens[-1] = operator
        elif self.tokens[-1] == "(":
            if operator == "-":
                self.entry = "-0"
                self.value = 0
            elif operator != "+":
                raise CalculatorError("Enter a number first")
        else:
            self.tokens.append(operator)

    def open_parenthesis(self) -> None:
        self._check_length()
        if self.just_evaluated:
            self.clear()
        if not self.tokens and self.entry == "0":
            self.entry = None
        self._commit_entry()
        if self.tokens and (isinstance(self.tokens[-1], int) or self.tokens[-1] == ")"):
            self.tokens.append("*")
        self.tokens.append("(")
        self.entry = None
        self.value = 0

    def close_parenthesis(self) -> None:
        depth = 0
        start = None
        for index in range(len(self.tokens) - 1, -1, -1):
            token = self.tokens[index]
            if token == ")":
                depth += 1
            elif token == "(":
                if depth == 0:
                    start = index
                    break
                depth -= 1
        if start is None:
            raise CalculatorError("No open parenthesis")
        candidate = self.tokens[start + 1:] + ([self.value] if self.entry is not None else [])
        result, _ = self._evaluate(candidate)
        self._commit_entry()
        self.tokens.append(")")
        self.value = result

    def _replace_operand(self, value: int) -> None:
        if self.just_evaluated:
            self.tokens = []
        elif self.entry is None and self.tokens and self.tokens[-1] == ")":
            depth = 0
            for index in range(len(self.tokens) - 1, -1, -1):
                token = self.tokens[index]
                if token == ")":
                    depth += 1
                elif token == "(":
                    depth -= 1
                    if depth == 0:
                        self.tokens = self.tokens[:index]
                        break
        self.value = self.normalize(value)
        self.entry = self.formatted()
        self.just_evaluated = False
        self.repeat = None
        self.last_expression = ""

    def clear_entry(self) -> None:
        self._replace_operand(0)

    def negate(self) -> None:
        was_negative_zero = self.entry == "-0"
        self._replace_operand(-self.value)
        if self.value == 0 and self.base == 10 and not was_negative_zero:
            self.entry = "-0"

    def bitwise_not(self) -> None:
        self._replace_operand(~self.value)

    def toggle_bit(self, bit: int) -> None:
        if not 0 <= bit < self.bits:
            raise ValueError("Bit is outside the selected word")
        self._replace_operand(self.value ^ (1 << bit))

    def backspace(self) -> None:
        if self.just_evaluated:
            self._replace_operand(self.value)
        if self.entry is None:
            if self.tokens and self.tokens[-1] in OPERATORS:
                self.tokens.pop()
                if self.tokens and isinstance(self.tokens[-1], int):
                    self.value = self.tokens.pop()
                    self.entry = self.formatted()
            elif self.tokens and self.tokens[-1] == "(":
                self.tokens.pop()
            return
        text = self.entry[:-1]
        self.entry = text if text not in ("", "-") else "0"
        self.value = self.normalize(int(self.entry, self.base))

    def set_base(self, base: int) -> None:
        if base not in (10, 16):
            raise ValueError("Unsupported base")
        self.base = base
        if self.entry is not None:
            self.entry = self.formatted()

    def set_bits(self, bits: int) -> None:
        if bits not in (8, 16, 32, 64):
            raise ValueError("Unsupported word size")
        self.bits = bits
        self.value = self.normalize(self.value)
        self.tokens = [self.normalize(token) if isinstance(token, int) else token
                       for token in self.tokens]
        if self.entry is not None:
            self.entry = self.formatted()
        self.repeat = None
        self.last_expression = ""

    def paste(self, text: str) -> None:
        if len(text) > 256:
            raise CalculatorError("Paste a single integer")
        compact = re.sub(r"[\s,_]", "", text).upper()
        source_base = 16 if compact.lstrip("+-").startswith("0X") else self.base
        pattern = r"[+-]?(?:0X)?[0-9A-F]+" if source_base == 16 else r"[+-]?[0-9]+"
        if not re.fullmatch(pattern, compact):
            raise CalculatorError("Paste a valid DEC or HEX integer")
        raw = int(compact, source_base)
        maximum = self.mask if source_base == 16 else (1 << (self.bits - 1)) - 1
        if not -(1 << (self.bits - 1)) <= raw <= maximum:
            raise CalculatorError(f"Input exceeds {self.bits}-bit range")
        self._replace_operand(raw)

    def _apply(self, operator: str, left: int, right: int) -> int:
        if operator == "+":
            result = left + right
        elif operator == "-":
            result = left - right
        elif operator == "*":
            result = left * right
        elif operator in ("/", "MOD"):
            if right == 0:
                raise CalculatorError("Cannot divide by zero")
            quotient = abs(left) // abs(right)
            if (left < 0) != (right < 0):
                quotient = -quotient
            result = quotient if operator == "/" else left - quotient * right
        elif operator == "AND":
            result = left & right
        elif operator == "OR":
            result = left | right
        elif operator == "XOR":
            result = left ^ right
        elif operator in ("<<", ">>"):
            if right < 0:
                raise CalculatorError("Shift count must be positive or zero")
            # Bound large shifts before creating an unnecessarily large integer.
            if right >= self.bits:
                result = -1 if operator == ">>" and left < 0 else 0
            else:
                result = left << right if operator == "<<" else left >> right
        else:
            raise ValueError("Unknown operator")
        return self.normalize(result)

    def _evaluate(self, tokens: list[int | str]) -> tuple[int, tuple[str, int] | None]:
        position = 0

        def expression(minimum: int = 0) -> tuple[int, tuple[str, int] | None]:
            nonlocal position
            if position >= len(tokens):
                raise CalculatorError("Complete the expression")
            token = tokens[position]
            position += 1
            repeat = None
            if isinstance(token, int):
                left = token
            elif token == "(":
                left, repeat = expression()
                if position >= len(tokens) or tokens[position] != ")":
                    raise CalculatorError("Close the parenthesis")
                position += 1
            else:
                raise CalculatorError("Enter a number first")
            while position < len(tokens):
                operator = tokens[position]
                if operator not in OPERATORS or OPERATORS[operator] < minimum:
                    break
                position += 1
                right, _ = expression(OPERATORS[operator] + 1)
                left = self._apply(operator, left, right)
                repeat = (operator, right)
            return left, repeat

        value, repeat = expression()
        if position != len(tokens):
            raise CalculatorError("Check the expression")
        return value, repeat

    def _format_tokens(self, tokens: list[int | str]) -> str:
        return " ".join(format_number(token, self.base, self.bits) if isinstance(token, int)
                        else SYMBOLS.get(token, token) for token in tokens)

    @property
    def expression_text(self) -> str:
        return self.last_expression or self._format_tokens(self.tokens)

    @property
    def live_expression_text(self) -> str:
        if self.just_evaluated or not self.tokens:
            return self.expression_text
        tokens = self.tokens + ([self.value] if self.entry is not None else [])
        return self._format_tokens(tokens)

    def _preview_tokens(self) -> list[int | str]:
        tokens = self.tokens + ([self.value] if self.entry is not None else [])
        # A trailing operator or empty group is still awaiting an operand.
        while tokens and (tokens[-1] in OPERATORS or tokens[-1] == "("):
            tokens.pop()
        if not tokens:
            return [self.value]
        tokens += [")"] * (tokens.count("(") - tokens.count(")"))
        return tokens

    def preview(self) -> int:
        """Evaluate the entered portion without committing or changing the input."""
        if self.just_evaluated:
            return self.value
        value, _ = self._evaluate(self._preview_tokens())
        return value

    def calculate(self, *, auto: bool = False) -> int:
        if self.just_evaluated and self.repeat:
            operator, right = self.repeat
            tokens = [self.value, operator, right]
        elif auto:
            tokens = self._preview_tokens()
        else:
            tokens = self.tokens[:] + ([self.value] if self.entry is not None else [])
            if not tokens:
                tokens = [self.value]
            if tokens[-1] in OPERATORS:
                tokens.append(self.value)
            tokens += [")"] * (tokens.count("(") - tokens.count(")"))
        value, repeat = self._evaluate(tokens)
        description = self._format_tokens(tokens) + " ="
        self.value = value
        self.repeat = repeat
        self.last_expression = description
        self.tokens = []
        self.entry = self.formatted()
        self.just_evaluated = True
        if repeat or len(tokens) > 1:
            self.history.insert(0, HistoryEntry(description, value, self.base, self.bits))
            del self.history[50:]
        return value

    def restore(self, item: HistoryEntry) -> None:
        self.clear()
        self.base = item.base
        self.bits = item.bits
        self.value = item.result
        self.entry = self.formatted()
        self.just_evaluated = True
