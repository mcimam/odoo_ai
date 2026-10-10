# Part of ci_ai.


def migrate(cr, version):
    """Reset chat routing away from the removed Cursor provider."""
    cr.execute(
        """
        UPDATE ci_ai_provider_config
           SET chat_provider = 'iap'
         WHERE chat_provider = 'cursor'
        """
    )
