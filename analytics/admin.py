from django.contrib import admin
from .models import Activity

# Register your models here.
class ActivityAdmin(admin.ModelAdmin):
    model = Activity


admin.site.register(Activity, ActivityAdmin)
