from django.core.management.base import BaseCommand, CommandError
from recognition.models import Student


class Command(BaseCommand):
    help = "Supprime toutes les donnees d'un etudiant (droit a l'effacement RGPD)"

    def add_arguments(self, parser):
        parser.add_argument('--email', type=str, required=True, help="Email de l'etudiant a supprimer")

    def handle(self, *args, **options):
        email = options['email']
        students = Student.objects.filter(email=email)

        if not students.exists():
            raise CommandError(f"Aucun etudiant trouve avec l'email : {email}")

        for student in students:
            name = student.get_full_name()
            if student.photo:
                student.photo.delete(save=False)
            student.delete()
            self.stdout.write(self.style.SUCCESS(f"Donnees supprimees pour {name} ({email})"))