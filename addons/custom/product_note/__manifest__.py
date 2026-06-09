{
    'name': 'Product Note',
    'version': '18.0.1.0.0',
    'category': 'Custom',
    'summary': 'Add a note field to the product template(learning module)',
    'depends': ['product'],
    'data': [
        'security/ir.model.access.csv',
        'views/product_note_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
    'author': 'khoa',
}