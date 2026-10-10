# Part of ci_ai.


def migrate(cr, version):
    """Rename settings inherit xml id to match parent (Odoo coding guidelines)."""
    cr.execute(
        """
        UPDATE ir_model_data
           SET name = 'res_config_settings_view_form'
         WHERE module = 'ci_ai'
           AND name = 'res_config_settings_view_form_ci_ai'
        """
    )
