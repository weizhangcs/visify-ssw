from django.apps import AppConfig

class MediaAssetsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    # 'name' 属性应指向你 App 的完整导入路径
    name = 'apps.media_assets'
    # 'verbose_name' 是在 Admin 后台中显示的名称
    verbose_name = '媒资资产管理'