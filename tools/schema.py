# 定义一个函数 _fn_tool , 接收名称、描述 属性和必需字段列表 返回一个字典
def _fn_tool(name:str,description:str,properties:dict,required:list[str])->dict:
    #返回一个包含类型和函数信息的字典
    return {
        # 设定类型为'function'
        'type':'function',
        #定义函数的具体内容
        'function':{
            #函数名称
            'name':name,
            #函数描述
            'description':description,
            # 参数设置 定义为一个对象 包含属性和必需字段
            'parameters':{'type':'object','properties':properties,'required':required}
        }
    }
    
# 定义一个工具列表 包含一个通过_fn_tool函数生成的工具 bash命令执行
TOOLS = [
    _fn_tool(
        'bash',
        '执行一条shell命令',
        {'command':{'type':'string'}},
        ['command']
    )
]