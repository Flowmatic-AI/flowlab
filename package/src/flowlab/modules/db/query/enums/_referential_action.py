from enum import StrEnum


class ReferentialActionEnum(StrEnum):
    """What a foreign key does to the referencing row when the referenced one moves.

    A member names the action alone: which event it answers to is decided by
    the parameter it is passed as, on_delete or on_update. These are also the
    spellings describe_table() reports back, so a described key can be handed
    straight to a builder.

    Only the actions every supported engine agrees on are listed. The standard's
    fifth, SET DEFAULT, is deliberately absent: MySQL accepts it, stores it and
    reports it back, but InnoDB never carries it out -- deleting the referenced
    row raises a foreign key violation instead of writing the default. It is
    left out rather than offered as a portability trap. A key that declares it
    anyway still describes, reaching you as the raw string.

    NO_ACTION and RESTRICT are not the same thing, close as they look. RESTRICT
    is checked the moment the referenced row moves; NO_ACTION waits until the
    end of the transaction when the constraint is DEFERRABLE INITIALLY DEFERRED,
    so a transaction that deletes a parent and then tidies up its children
    commits under NO_ACTION and is refused under RESTRICT. MySQL alone cannot
    tell them apart, having no deferred checks. NO_ACTION also earns its place
    by being what all three engines report for a key that declares no rule at
    all, which is most of them.
    """

    NO_ACTION = "NO ACTION"
    RESTRICT = "RESTRICT"
    CASCADE = "CASCADE"
    SET_NULL = "SET NULL"
