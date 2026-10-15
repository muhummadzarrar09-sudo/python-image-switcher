"""Still-photo batch editor: reversible sessions and portable project copies.

The converter remains a separate workflow. The editor deliberately excludes
animations, videos and documents instead of silently editing one frame/page.
"""

from .batch import BatchSession, Photo
from .project import PhotoProject, create_project, read_project
from .workflow import export_batch, import_project

__all__ = ["BatchSession", "Photo", "PhotoProject", "create_project", "read_project", "export_batch", "import_project"]
