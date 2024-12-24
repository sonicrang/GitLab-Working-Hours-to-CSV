import csv
import pytz
import gitlab
import urllib3
import requests
from datetime import datetime

urllib3.disable_warnings()

def main():
    # 获取输入
    while True:
        start_time_str = input("请输入起始统计时间（格式为2024-05-20 00:00:00）：")
        try:
            start_time_utc_e8 = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=pytz.timezone('Asia/Shanghai'))
            start_time_utc = start_time_utc_e8.astimezone(pytz.utc)
            break
        except ValueError:
            print("输入格式错误，请重新输入！")
    
    while True:
        end_time_str = input("请输入终止统计时间（格式为2024-05-20 23:59:59）：")
        try:
            end_time_utc_e8 = datetime.strptime(end_time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=pytz.timezone('Asia/Shanghai'))
            end_time_utc = end_time_utc_e8.astimezone(pytz.utc)
            break
        except ValueError:
            print("输入格式错误，请重新输入！")

    # 加载配置
    gl = gitlab.Gitlab.from_config('gitlab', ['gitlab.cfg'])
    # 创建csv
    header = ["群组名称", "项目名称", "议题标题", "议题权重", "预估工时（小时）",  "用户名", "实际工时（小时）"]
    with open('report.csv', 'w', newline='', encoding='gbk') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(header) 
        get_groups(gl, writer, start_time_utc, end_time_utc)
    print("导出完成！")

def get_groups(gl: gitlab.Gitlab, writer, start_time_utc: datetime, end_time_utc: datetime):
    per_page = 100
    page = 1
    while True:
        groups = gl.groups.list(per_page=per_page, page=page)
        if len(groups) == 0:
            break
        for group in groups:
            print("群组：", group.full_name)
            get_projects(gl, writer, group, start_time_utc, end_time_utc)
        page += 1
        
def get_projects(gl: gitlab.Gitlab, writer, group, start_time_utc: datetime, end_time_utc: datetime):
    per_page = 100
    page = 1
    while True:
        projects = group.projects.list(per_page=per_page, page=page)
        if len(projects) == 0:
            break
        for project in projects:
            print("项目：",project.name)
            get_issues_in_time_period(gl, writer, group.full_name, project, start_time_utc, end_time_utc)
        page += 1

# 获取指定时间范围内的issue
def get_issues_in_time_period(gl: gitlab.Gitlab, writer, group_full_name: str, project, start_time_utc: datetime, end_time_utc: datetime):
    project = gl.projects.get(project.id)
    per_page = 100
    page = 1
    while True:
        issues = project.issues.list(per_page=per_page, page=page, updated_after=start_time_utc.isoformat(), updated_before=end_time_utc.isoformat())
        if len(issues) == 0:
            break
        for issue in issues:
            print("issue:", issue.title)
            timelogs = get_timelogs(gl, issue, start_time_utc, end_time_utc)
            # 写入csv
            for key, value in timelogs.items():
                print(f'user: {key}, spendtime: {value}')
                data = [group_full_name, project.name, issue.title, issue.weight, round(issue.time_stats()['time_estimate']/3600,2) , key, round(value/3600,2)]
                writer.writerow(data)
        page += 1

# 使用Graphql获取工时详细信息
def get_timelogs(gl: gitlab.Gitlab, issue, start_time_utc: datetime, end_time_utc: datetime):
    GITLAB_GRAPHQL_ENDPOINT = f'{gl.url}/api/graphql'
    headers = {
        'Authorization': f'Bearer {gl.private_token}',
        'Content-Type': 'application/json'
    }
    QUERY = '''
    query ($issue_id: IssueID!){
        issue(id: $issue_id) {
            id 
            timelogs {
                nodes {
                    spentAt 
                    timeSpent 
                    user {
                        username
                    }
                }
            }
        }
    }
    '''
    payload = {
        "query": QUERY,
        "variables": {
            "issue_id": f'gid://gitlab/Issue/{issue.id}',
        }
    }
    response = requests.post(GITLAB_GRAPHQL_ENDPOINT, json=payload, headers=headers)
    results = {}
    if response.status_code == 200:
        data = response.json()
        timelogs = data['data']['issue']['timelogs']['nodes']
        for timelog in timelogs:
            spent_at = timelog['spentAt']
            time_spent = timelog['timeSpent']
            username = timelog['user']['username']
            # 格式化时间
            spent_at_utc = datetime.strptime(spent_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.utc)
            # 获取员工在时间范围内的总工时
            if spent_at_utc > start_time_utc and spent_at_utc < end_time_utc:
                if username not in results:
                    results[username] = time_spent
                else:
                    results[username] = results[username] + time_spent
        return results
    else:
        print(f"Error fetching GitLab Timelogs: {response.status_code} - {response.text}")
        return {}


if __name__ == '__main__':
    main()