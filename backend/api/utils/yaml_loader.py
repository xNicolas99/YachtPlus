"""Bound YAML parsing before object construction."""
import yaml
from fastapi import HTTPException

def load_yaml(content):
    try:
        depth = 0
        for count, token in enumerate(yaml.scan(content)):
            if isinstance(token, yaml.tokens.AliasToken):
                raise HTTPException(422, "YAML aliases are not supported; inline their values")
            if isinstance(token, (yaml.tokens.BlockMappingStartToken, yaml.tokens.BlockSequenceStartToken,
                                  yaml.tokens.FlowMappingStartToken, yaml.tokens.FlowSequenceStartToken)):
                depth += 1
            elif isinstance(token, (yaml.tokens.BlockEndToken, yaml.tokens.FlowMappingEndToken, yaml.tokens.FlowSequenceEndToken)):
                depth -= 1
            if depth > 50 or count > 100000:
                raise HTTPException(422, "YAML document is too complex")
        return yaml.safe_load(content)
    except yaml.YAMLError:
        raise HTTPException(422, "Invalid YAML document") from None
