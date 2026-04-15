import os
from modules.error_solver import generate_corrected_pdf

output = "test_indic.pdf"
res = generate_corrected_pdf("नमस्ते ભારત", output)
print(f"Result: {res}")
