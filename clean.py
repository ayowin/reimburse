
import os
import shutil
import sys

def clean_pycache():
    """清理所有__pycache__目录"""
    count = 0
    for root, dirs, files in os.walk('.'):
        if '__pycache__' in dirs:
            pycache_path = os.path.join(root, '__pycache__')
            shutil.rmtree(pycache_path)
            count += 1
            print(f"已删除: {pycache_path}")
    print(f"共清理了 {count} 个 __pycache__ 目录")
    return count

def clean_uploads():
    """清理uploads文件夹"""
    uploads_path = 'uploads'
    if os.path.exists(uploads_path):
        # 删除uploads文件夹下的所有文件和子文件夹
        for filename in os.listdir(uploads_path):
            file_path = os.path.join(uploads_path, filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
                    print(f"已删除文件: {file_path}")
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
                    print(f"已删除目录: {file_path}")
            except Exception as e:
                print(f"删除 {file_path} 时出错: {e}")
        print(f"已清理 {uploads_path} 文件夹")
        return True
    else:
        print(f"{uploads_path} 文件夹不存在")
        return False

def clean_database():
    """清理reimburse.db文件"""
    db_path = 'reimburse.db'
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"已删除: {db_path}")
        return True
    else:
        print(f"{db_path} 文件不存在")
        return False

def main():
    print("开始清理...")
    print("-" * 50)

    # 清理__pycache__
    print("清理 __pycache__ 目录:")
    clean_pycache()

    # 清理uploads文件夹
    print("清理 uploads 文件夹:")
    clean_uploads()

    # 清理数据库文件
    print("清理数据库文件:")
    clean_database()

    print("-" * 50)
    print("清理完成!")

if __name__ == '__main__':
    main()
