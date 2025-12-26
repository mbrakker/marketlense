from pdf2image.pdf2image import pdfinfo_from_path, convert_from_path

poppler_bin = r"C:\Users\Михаил\AppData\Local\Microsoft\WinGet\Packages\oschwartz10612.Poppler_Microsoft.Winget.Source_8wekyb3d8bbwe\poppler-25.07.0\Library\bin"
pdf = r"cache\1snMTUyfA1GMDKMMT5Y8XZs8kivti7m1f.pdf"

print('pdfinfo_from_path ->')
print(pdfinfo_from_path(pdf, poppler_path=poppler_bin))

print('\nconvert_from_path -> (dpi=50, pages 1..1)')
images = convert_from_path(pdf, poppler_path=poppler_bin, dpi=50, first_page=1, last_page=1, fmt='ppm')
print('Converted', len(images), 'images')
for i, im in enumerate(images):
    print('Image', i, 'mode', im.mode, 'size', im.size)
