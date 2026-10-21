import pymysql

pymysql.version_info = (2, 2, 1, "final", 0)
pymysql.install_as_MySQLdb()

# Django 6.x requires MySQL 8.4+ by default; bypass check to allow MySQL 8.0.x
from django.db.backends.mysql.base import DatabaseWrapper
DatabaseWrapper.check_database_version_supported = lambda self: None
