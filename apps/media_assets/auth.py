# 文件路径: apps/media_assets/auth.py

from django.contrib.auth.models import User


def create_vss_user(claims):
    """
    一个自定义的用户创建函数，用于处理从 Authentik 返回的 claims。
    它将强制使用 email 作为 username，并为指定用户自动提升权限。
    """
    # 打印接收到的原始 claims，这是最关键的调试信息
    print(f"--- AUTHENTIK CLAIMS RECEIVED ---: {claims}")

    email = claims.get('email')

    # 如果 Authentik 没有发送 email，我们无法继续
    if not email:
        print("Error: Email claim not found in Authentik response. Aborting user creation.")
        # 返回 None 会中断登录流程并显示一个通用错误页
        return None

    # [修正] 强制使用 email 作为 username 来创建或获取用户
    user, created = User.objects.get_or_create(username=email, defaults={'email': email})

    if created:
        user.first_name = claims.get('given_name', '')
        user.last_name = claims.get('family_name', claims.get('name', ''))

        # 【关键】自动授权逻辑：
        # [重要] ==> 请将下面的 'your-real-admin-email@example.com' 替换为您自己的管理员邮箱
        if user.email == '920698540@qq.com':
            user.is_staff = True
            user.is_superuser = True
            print(f"User '{email}' has been granted superuser privileges.")

        user.save()
        print(f"New user '{email}' created from Authentik claims.")

    return user