from fastapi import HTTPException, status


def http_exception(status_code: int, detail: str):
    return HTTPException(status_code=status_code, detail=detail)


credentials_exception = http_exception(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
)

not_found_exception = http_exception(
    status_code=status.HTTP_404_NOT_FOUND, detail="Item not found"
)

forbidden_exception = http_exception(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="You do not have permission to access this resource",
)
