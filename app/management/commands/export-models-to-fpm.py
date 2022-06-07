import os
from django.core.management.base import BaseCommand, CommandError
import django.apps
import inspect
from pathlib import Path


def find_upwards(cwd: Path, filename: str) -> Path:
    if cwd == Path(cwd.root):
        return None

    fullpath = cwd / filename

    return fullpath if fullpath.exists() else find_upwards(cwd.parent, filename)


class Command(BaseCommand):
    help = "Closes the specified poll for voting"

    def add_arguments(self, parser):
        parser.add_argument("--app", type=str, required=True)
        parser.add_argument("export_path", type=str)

    def handle(self, *args, **options):
        app = options["app"]
        export_path = options["export_path"]
        current_dir = os.getcwd()
        rel_path = os.path.join(current_dir, export_path)
        abs_path = Path(os.path.abspath(rel_path))

        # Check whether actual fpm project. If yes, the path has to be relative to all this.
        # If no, exit with error.
        fpm_project_root = find_upwards(abs_path, "FPM.ftd")
        if fpm_project_root is None:
            raise CommandError("This command can only export to an FPM project.")
        fpm_project_root = os.path.dirname(fpm_project_root)
        os.makedirs(abs_path, exist_ok=True)

        all_models = django.apps.apps.all_models[app]
        os.makedirs(os.path.join(abs_path, app), exist_ok=True)
        successful_exports = {}
        for (k, v) in all_models.items():
            export_path = os.path.join(abs_path, app, f"{k}.ftd")
            doc_url = (
                export_path.replace(fpm_project_root, "").lstrip("/").rstrip(".ftd")
            )
            lines = inspect.getsource(v)
            class_name = v.__name__
            export_content = f"-- ft.page-with-toc: `{class_name} Model`\ntoc: $config.development\n\n-- ft.code:\nlang: py\n\n{lines}"
            with open(export_path, "w") as f:
                f.write(export_content)
                self.stdout.write(
                    self.style.SUCCESS(f"Successfully exported models to {abs_path}")
                )
                successful_exports[class_name] = doc_url
        index_path = os.path.join(abs_path, app, "index.ftd")
        with open(index_path, "w") as f:
            doc_url = (
                index_path.replace(fpm_project_root, "").lstrip("/").rstrip(".ftd")
            )
            f.write(
                f"-- ft.page-with-toc: `{app} Models`\ntoc: $config.development\n\n"
            )
            self.stdout.write(
                self.style.SUCCESS(f"Export successful. Add the following to your TOC")
            )
            self.stdout.write(f"- {app} Models: {os.path.dirname(doc_url)}")
            for export in successful_exports:
                resp_line = f"- {export} Model: {successful_exports[export]}\n"
                f.write(resp_line)
                self.stdout.write(f"  {resp_line}")

            # with open("{export_path}/" , "a") as f:
        # for poll_id in options["poll_ids"]:
        #     try:
        #         poll = Poll.objects.get(pk=poll_id)
        #     except Poll.DoesNotExist:
        #         raise CommandError('Poll "%s" does not exist' % poll_id)

        #     poll.opened = False
        #     poll.save()

        #     self.stdout.write(
        #         self.style.SUCCESS('Successfully closed poll "%s"' % poll_id)
        #     )
