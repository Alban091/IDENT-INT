from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models import Student


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ['photo_preview', 'full_name', 'school', 'year', 'email', 'has_encoding', 'created_at']
    list_filter = ['school', 'year', 'created_at']
    search_fields = ['first_name', 'last_name', 'email']
    readonly_fields = ['photo_preview_large', 'face_encoding', 'created_at', 'updated_at']

    fieldsets = (
        ('📋 Informations personnelles', {
            'fields': ('first_name', 'last_name', 'email')
        }),
        ('🎓 Informations académiques', {
            'fields': ('school', 'year', 'promotion')
        }),
        ('📸 Photo', {
            'fields': ('photo', 'photo_preview_large', 'photo_url')
        }),
        ('🤖 Données IA', {
            'fields': ('face_encoding',),
            'classes': ('collapse',)
        }),
        ('📅 Métadonnées', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def photo_preview(self, obj):
        """Miniature de la photo dans la liste"""
        if obj.photo:
            html = f'<img src="{obj.photo.url}" width="50" height="50" style="object-fit: cover; border-radius: 50%; border: 2px solid #00ff88;" />'
            return mark_safe(html)
        html = '<div style="width: 50px; height: 50px; border-radius: 50%; background: #333; display: flex; align-items: center; justify-content: center; color: white; font-size: 20px;">?</div>'
        return mark_safe(html)

    photo_preview.short_description = "Photo"

    def photo_preview_large(self, obj):
        """Grande photo dans le détail"""
        if obj.photo:
            html = f'<img src="{obj.photo.url}" style="max-width: 300px; border-radius: 15px; box-shadow: 0 5px 20px rgba(0,0,0,0.2);" />'
            return mark_safe(html)
        return "Pas de photo"

    photo_preview_large.short_description = "Aperçu photo"

    def full_name(self, obj):
        """Nom complet avec style"""
        html = f'<strong style="color: #00ff88;">{obj.get_full_name()}</strong>'
        return mark_safe(html)

    full_name.short_description = "Nom complet"
    full_name.admin_order_field = 'last_name'

    def has_encoding(self, obj):

        if obj.face_encoding:
            html = '<span style="color: #00ff88;">✓ Encodé</span>'
            return mark_safe(html)
        html = '<span style="color: #ff6b6b;">✗ Non encodé</span>'
        return mark_safe(html)

    has_encoding.short_description = "Encodage IA"

    actions = ['encode_faces']

    def encode_faces(self, request, queryset):

        from .face_recognition_utils import encode_student_faces

        count = 0
        for student in queryset:
            if encode_student_faces(student):
                count += 1

        self.message_user(request, f"{count} étudiant(s) encodé(s) avec succès.")

    encode_faces.short_description = "🤖 Encoder les visages sélectionnés"


# Personnaliser le site admin
admin.site.site_header = "TSP IDENTINT - Administration"
admin.site.site_title = "TSP IDENTINT Admin"
admin.site.index_title = "Gestion de la reconnaissance faciale"