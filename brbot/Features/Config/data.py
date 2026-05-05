from enum import Enum


class ConfigKeys(Enum):
    ALLOW_PHRASES = "Allow Phrase-Based Responses"
    LIMIT_USER_RESPONSES = "Limit # of User Responses"
    MAX_USER_RESPONSES = "Maximum # of User Responses"
    RESTRICT_RESPONSE_DELETION = "Responses Editable only by Author"
    ENABLE_NSFW = "Enable NSFW Content (limits some commands to NSFW channels)"
