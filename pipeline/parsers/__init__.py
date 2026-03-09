from pipeline.parsers.base import BaseParser
from pipeline.parsers.hdfc_savings import HDFCSavingsParser

PARSER_REGISTRY: dict[str, type[BaseParser]] = {
    "hdfc_savings": HDFCSavingsParser,
}
