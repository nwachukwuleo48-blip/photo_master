import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_contact_email(*, name, email, message, phone=None, event=None):
    sender_email = os.getenv("EMAIL_USER")
    sender_password = os.getenv("EMAIL_PASS")
    receiver_email = os.getenv("EMAIL_RECEIVER") or sender_email

    if not sender_email or not sender_password or not receiver_email:
        raise RuntimeError("Missing EMAIL_USER/EMAIL_PASS/EMAIL_RECEIVER environment variables")

    subject = f"New Contact Message from {name}"
    body = (
        "New message from website contact form\n\n"
        f"Name: {name}\n"
        f"Email: {email}\n"
        f"Phone: {phone or 'N/A'}\n"
        f"Shoot Type: {event or 'N/A'}\n\n"
        "Message:\n"
        f"{message}\n"
    )

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = receiver_email
    msg["Subject"] = subject
    msg["Reply-To"] = email
    msg.attach(MIMEText(body, "plain"))

    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(sender_email, sender_password)
    server.send_message(msg)
    server.quit()


def send_gallery_access_email(*, to_email, client_name, gallery_link, access_code, studio_name="StillPhotos"):
    sender_email = os.getenv("EMAIL_USER")
    sender_password = os.getenv("EMAIL_PASS")

    if not sender_email or not sender_password:
        raise RuntimeError("Missing EMAIL_USER/EMAIL_PASS environment variables")

    subject = f"Your Private Gallery Is Ready - {studio_name}"
    body = (
        f"Hi {client_name},\n\n"
        "Your private gallery is ready.\n\n"
        f"Gallery link: {gallery_link}\n"
        f"Access code: {access_code}\n\n"
        "How to view:\n"
        "1) Open the link\n"
        "2) Enter the access code\n"
        "3) Download your photos (you can use 'Download All')\n\n"
        f"Thank you,\n{studio_name}\n"
    )

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(sender_email, sender_password)
    server.send_message(msg)
    server.quit()








