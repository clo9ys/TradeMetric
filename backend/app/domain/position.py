from app.domain.errors import InvalidQuantityError

MIN_QUANTITY = -(2**63)
MAX_QUANTITY = 2**63 - 1


def validate_quantity(value: int) -> int:
    if type(value) is not int or value == 0:
        raise InvalidQuantityError("Количество облигаций должно быть ненулевым целым числом")
    if not MIN_QUANTITY <= value <= MAX_QUANTITY:
        raise InvalidQuantityError("Количество облигаций выходит за пределы жопустимых значений")
    return value
