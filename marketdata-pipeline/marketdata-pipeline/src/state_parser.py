def fetch_state_doc(drive_service: Resource, state_doc_id: str) -> str:
    """Holt das STATE-Doc als Markdown-Text via Drive API.

    Unterstützt zwei Formate:
    - Google Doc (application/vnd.google-apps.document) → export als text/plain
    - Markdown-Datei (text/markdown) oder Plain-Text → direkt download
    """
    # Erst Metadaten holen, um mimeType zu erfahren
    metadata = drive_service.files().get(
        fileId=state_doc_id,
        fields="mimeType,name",
        supportsAllDrives=True,
    ).execute()
    mime_type = metadata.get("mimeType", "")

    if mime_type == "application/vnd.google-apps.document":
        # Google Doc → export als plain text
        request = drive_service.files().export_media(
            fileId=state_doc_id,
            mimeType="text/plain",
        )
    else:
        # Markdown, Plain-Text, etc. → direkt herunterladen
        request = drive_service.files().get_media(
            fileId=state_doc_id,
            supportsAllDrives=True,
        )

    content = request.execute()
    if isinstance(content, bytes):
        content = content.decode("utf-8")
    return content
