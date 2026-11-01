import unittest

from programmer_calculator.engine import Calculator, CalculatorError, format_number


class CalculatorTests(unittest.TestCase):
    def setUp(self):
        self.calc = Calculator()

    def enter(self, text):
        for digit in text:
            self.calc.input_digit(digit)

    def binary(self, left, operator, right):
        self.calc.paste(str(left))
        self.calc.operator(operator)
        self.calc.paste(str(right))
        return self.calc.calculate()

    def test_arithmetic_precedence_and_repeat_equals(self):
        self.enter("2")
        self.calc.operator("+")
        self.enter("3")
        self.calc.operator("*")
        self.enter("4")
        self.assertEqual(self.calc.calculate(), 14)
        self.assertEqual(self.calc.calculate(), 26)

    def test_preview_preserves_editable_entry_and_history(self):
        self.enter("2")
        self.calc.operator("+")
        self.enter("3")
        self.assertEqual(self.calc.preview(), 5)
        self.assertEqual(self.calc.live_expression_text, "2 + 3")
        self.enter("4")
        self.assertEqual(self.calc.preview(), 36)
        self.assertEqual(self.calc.live_expression_text, "2 + 34")
        self.assertEqual(self.calc.history, [])
        self.calc.backspace()
        self.assertEqual(self.calc.preview(), 5)
        self.assertEqual(self.calc.calculate(), 5)
        self.assertEqual(len(self.calc.history), 1)
        self.assertEqual(self.calc.preview(), 5)
        self.assertEqual(self.calc.calculate(), 8)

    def test_preview_keeps_running_total_after_trailing_operator(self):
        for expected in range(1, 7):
            self.enter("1")
            self.assertEqual(self.calc.preview(), expected)
            self.calc.operator("+")
            self.assertEqual(self.calc.preview(), expected)
        self.assertEqual(self.calc.calculate(auto=True), 6)
        self.assertEqual(self.calc.history[0].result, 6)
        self.assertEqual(self.calc.calculate(auto=True), 7)

    def test_preview_handles_unfinished_parentheses_and_precedence(self):
        self.enter("2")
        self.calc.operator("*")
        self.calc.open_parenthesis()
        self.assertEqual(self.calc.preview(), 2)
        self.enter("3")
        self.calc.operator("+")
        self.assertEqual(self.calc.preview(), 6)
        self.enter("4")
        self.assertEqual(self.calc.preview(), 14)
        self.calc.close_parenthesis()
        self.assertEqual(self.calc.calculate(), 14)

    def test_preview_error_can_be_corrected_by_continuing_to_type(self):
        self.enter("8")
        self.calc.operator("/")
        self.enter("0")
        with self.assertRaisesRegex(CalculatorError, "zero"):
            self.calc.preview()
        self.enter("2")
        self.assertEqual(self.calc.preview(), 4)
        self.assertEqual(self.calc.calculate(), 4)

    def test_left_associativity(self):
        self.enter("20")
        self.calc.operator("-")
        self.enter("5")
        self.calc.operator("-")
        self.enter("3")
        self.assertEqual(self.calc.calculate(), 12)

    def test_nested_parentheses_and_implicit_multiplication(self):
        self.enter("2")
        self.calc.open_parenthesis()
        self.enter("3")
        self.calc.operator("+")
        self.calc.open_parenthesis()
        self.enter("4")
        self.calc.operator("*")
        self.enter("5")
        self.calc.close_parenthesis()
        self.calc.close_parenthesis()
        self.assertEqual(self.calc.value, 23)
        self.assertEqual(self.calc.calculate(), 46)

    def test_equals_closes_parentheses(self):
        self.calc.open_parenthesis()
        self.enter("7")
        self.calc.operator("+")
        self.enter("8")
        self.assertEqual(self.calc.calculate(), 15)

    def test_invalid_parenthesis_is_recoverable(self):
        self.enter("7")
        with self.assertRaises(CalculatorError):
            self.calc.close_parenthesis()
        self.assertEqual(self.calc.value, 7)
        self.assertEqual(self.calc.calculate(), 7)

    def test_switching_bases_preserves_pending_expression(self):
        self.enter("255")
        self.calc.operator("+")
        self.calc.set_base(16)
        self.enter("A")
        self.assertEqual(self.calc.calculate(), 265)
        self.assertEqual(self.calc.formatted(), "109")
        self.calc.set_base(10)
        self.assertEqual(self.calc.formatted(), "265")

    def test_full_64_bit_precision(self):
        self.assertEqual(self.binary(9007199254740993, "+", 2), 9007199254740995)
        self.calc.clear()
        self.assertEqual(self.binary(9223372036854775807, "/", 3), 3074457345618258602)

    def test_signed_division_and_remainder_truncate_toward_zero(self):
        for left, right, quotient, remainder in ((-7, 3, -2, -1), (7, -3, -2, 1), (-7, -3, 2, -1)):
            with self.subTest(left=left, right=right):
                self.calc.clear()
                self.assertEqual(self.binary(left, "/", right), quotient)
                self.calc.clear()
                self.assertEqual(self.binary(left, "MOD", right), remainder)

    def test_signed_overflow_at_every_word_size(self):
        for bits in (8, 16, 32, 64):
            with self.subTest(bits=bits):
                self.calc = Calculator(bits=bits)
                maximum = (1 << (bits - 1)) - 1
                self.assertEqual(self.binary(maximum, "+", 1), -(1 << (bits - 1)))
                self.assertEqual(self.calc.formatted(16), "8" + "0" * (bits // 4 - 1))

    def test_hex_all_ones_is_negative_one(self):
        for bits in (8, 16, 32, 64):
            self.calc = Calculator(bits=bits, base=16)
            self.enter("F" * (bits // 4))
            self.assertEqual(self.calc.value, -1)
            self.calc.set_base(10)
            self.assertEqual(self.calc.formatted(), "-1")

    def test_rejected_overflow_does_not_mutate_input(self):
        self.calc = Calculator(bits=8)
        self.enter("12")
        with self.assertRaises(CalculatorError):
            self.enter("8")
        self.assertEqual(self.calc.value, 12)
        self.enter("7")
        self.assertEqual(self.calc.value, 127)

    def test_typing_signed_minimum(self):
        self.calc = Calculator(bits=8)
        self.calc.negate()
        self.enter("128")
        self.assertEqual(self.calc.value, -128)
        self.calc.negate()
        self.assertEqual(self.calc.value, -128)

    def test_invalid_decimal_hex_digit_is_ignored(self):
        self.enter("123AF")
        self.assertEqual(self.calc.value, 123)

    def test_changing_width_wraps_and_widening_sign_extends(self):
        self.enter("255")
        self.calc.set_bits(8)
        self.assertEqual(self.calc.value, -1)
        self.calc.set_bits(64)
        self.assertEqual(self.calc.formatted(16), "FFFFFFFFFFFFFFFF")

    def test_bitwise_operators(self):
        for operator, expected in (("AND", 8), ("OR", 14), ("XOR", 6)):
            self.calc.clear()
            self.assertEqual(self.binary(12, operator, 10), expected)
        self.calc.clear()
        self.calc.bitwise_not()
        self.assertEqual(self.calc.value, -1)
        self.calc.toggle_bit(63)
        self.assertEqual(self.calc.value, 9223372036854775807)

    def test_shift_sign_extension_and_large_counts(self):
        for left, operator, right, expected in ((-8, ">>", 2, -2), (7, "<<", 3, 56),
                                                  (-8, ">>", 64, -1), (1, "<<", 9223372036854775807, 0)):
            self.calc.clear()
            self.assertEqual(self.binary(left, operator, right), expected)
        self.calc.clear()
        with self.assertRaises(CalculatorError):
            self.binary(1, "<<", -1)

    def test_division_error_can_be_corrected_with_clear_entry(self):
        self.enter("9")
        self.calc.operator("/")
        self.enter("0")
        with self.assertRaisesRegex(CalculatorError, "zero"):
            self.calc.calculate()
        self.calc.clear_entry()
        self.enter("3")
        self.assertEqual(self.calc.calculate(), 3)

    def test_operator_replacement(self):
        self.enter("7")
        self.calc.operator("+")
        self.calc.operator("*")
        self.enter("3")
        self.assertEqual(self.calc.calculate(), 21)

    def test_clear_entry_preserves_pending_operation(self):
        self.enter("7")
        self.calc.operator("+")
        self.enter("123")
        self.calc.clear_entry()
        self.enter("2")
        self.assertEqual(self.calc.calculate(), 9)

    def test_editing_and_starting_new_calculation(self):
        self.enter("123")
        self.calc.backspace()
        self.assertEqual(self.calc.value, 12)
        self.calc.calculate()
        self.enter("4")
        self.assertEqual(self.calc.value, 4)
        self.assertEqual(self.calc.calculate(), 4)

    def test_unary_operation_on_parenthesized_value(self):
        self.enter("2")
        self.calc.operator("*")
        self.calc.open_parenthesis()
        self.enter("3")
        self.calc.operator("+")
        self.enter("4")
        self.calc.close_parenthesis()
        self.calc.negate()
        self.assertEqual(self.calc.calculate(), -14)

    def test_safe_pasting(self):
        for text, expected in (("0xFF", 255), ("9,007,199,254,740,993", 9007199254740993),
                               ("-42", -42), ("1_024", 1024)):
            self.calc.paste(text)
            self.assertEqual(self.calc.value, expected)
        for text in ("1+2", "hello", "0x", "1.5", "2 ** 8", "9" * 257):
            with self.subTest(text=text[:20]), self.assertRaises(CalculatorError):
                self.calc.paste(text)
        self.assertEqual(self.calc.value, 1024)

    def test_history_restores_base_width_and_value(self):
        self.calc = Calculator(bits=8, base=16)
        self.enter("7F")
        self.calc.operator("+")
        self.enter("1")
        self.calc.calculate()
        entry = self.calc.history[0]
        self.calc.set_bits(64)
        self.calc.set_base(10)
        self.calc.clear()
        self.assertEqual(len(self.calc.history), 1)
        self.calc.restore(entry)
        self.assertEqual((self.calc.bits, self.calc.base, self.calc.value), (8, 16, -128))
        self.calc.operator("+")
        self.enter("1")
        self.assertEqual(self.calc.calculate(), -127)

    def test_grouped_formatting(self):
        self.assertEqual(format_number(123456789, grouped=True), "123,456,789")
        self.assertEqual(format_number(-1, 16, 64, grouped=True), "FFFF FFFF FFFF FFFF")


if __name__ == "__main__":
    unittest.main()
