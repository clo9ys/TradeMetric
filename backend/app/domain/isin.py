import re

from app.domain.errors import InvalidISINError

ISIN_PATTERN = re.compile(r"[A-Z]{2}[A-Z0-9]{9}[0-9]\Z")


def validate_isin(value: str) -> str:
    if not isinstance(value, str):
        raise InvalidISINError("ISIN должен быть строкой")

    isin = value.strip().upper()
    if not ISIN_PATTERN.fullmatch(isin):
        raise InvalidISINError("ISIN должен состоять из 12 допустимых символов")

    digits = "".join(character if character.isdigit() else str(ord(character) - 55) for character in isin)
    checksum = 0

    # по алгоритму Луна проверяем веалидный ли это ISIN
    for index, character in enumerate(reversed(digits)):
        number = int(character)
        if index % 2 == 1:
            number *= 2
            if number > 9:
                number -= 9
        checksum += number

    if checksum % 10 != 0:
        raise InvalidISINError("Неверная контрольная цифра ISIN")

    return isin
