import fitz  # PyMuPDF
import re

def parse_resume(pdf_path: str) -> dict:
    try:
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text()
        
        data = {
            "name": "",
            "email": "",
            "phone": "",
            "skills": [],
            "experience": [],
            "education": [],
            "projects": []
        }
        
        # Extract full name
        name_match = re.search(r'([A-Z][a-z]+\s[A-Z][a-z]+)', text)
        if name_match:
            data["name"] = name_match.group(1)
        
        # Extract email
        email_match = 
re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
        if email_match:
            data["email"] = email_match.group(0)
        
        # Extract phone
        phone_match = re.search(r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b', text)
        if phone_match:
            data["phone"] = phone_match.group(0)
        
        # Extract skills
        skills_match = re.search(r'Skills:\s*(.*)', text, re.IGNORECASE)
        if skills_match:
            data["skills"] = skills_match.group(1).split(',')
        
        # Extract experience
        experience_match = 
re.findall(r'([A-Z][a-z]+\s[A-Z][a-z]+)\s+\d{4}\s*-\s*\d{4}\s*:\s*(.*)', text)
        if experience_match:
            data["experience"] = [{"company": name, "position": pos} for name, 
pos in experience_match]
        
        # Extract education
        education_match = 
re.findall(r'([A-Z][a-z]+\s[A-Z][a-z]+)\s+\d{4}\s*-\s*\d{4}\s*:\s*(.*)', text)
        if education_match:
            data["education"] = [{"degree": name, "institution": pos} for name, 
pos in education_match]
        
        # Extract projects
        projects_match = re.findall(r'Projects:\s*(.*)', text, re.IGNORECASE)
        if projects_match:
            data["projects"] = projects_match[0].split(',')
        
        return data
    
    except Exception as e:
        print(f"Error parsing PDF: {e}")
        return {}